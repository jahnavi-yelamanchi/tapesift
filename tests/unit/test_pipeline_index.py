"""E7 per-asset glue (docs/specs/30-runner.md, test_pipeline_index.py): config resolution (M1 R9)
and index_asset against a stub decoder and fake models. No real model, no real decode (ADR 0008)."""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Literal

import numpy as np
import pytest
from tests.fakes import FakeASR, FakeVAD, FakeVLM

from tapesift.cli.doctor import Probes
from tapesift.config import Config, ModelLoadError, Profile, VlmConfig
from tapesift.media.types import (
    AssetInfo,
    AudioChunk,
    AudioStreamInfo,
    DecodeError,
    Frame,
    VideoInfo,
)
from tapesift.schema.records import AssetRecord, Utterance
from tapesift.warning_codes import WarningCode, WarningSink

# isort: split
import tapesift.pipeline.index as pi
from tapesift.pipeline.index import Backends, index_asset

SR = 16_000
Z = "0" * 40
_TONE = 0.3 * np.sin(2 * np.pi * 440 * np.arange(int(0.3 * SR)) / SR)
BURSTS = np.tile(np.concatenate([_TONE, np.zeros(int(0.2 * SR))]), 4).astype(np.float32)
ASSET = AssetInfo(
    "tsid1:" + "0" * 64,
    Path("/x/a.mp4"),
    2.0,
    VideoInfo(0, "h264", 64, 48, 25.0, False, 0),
    (AudioStreamInfo(1, "aac", None, True),),
    (),
)
ASSET_NO_AUDIO = AssetInfo(ASSET.id, ASSET.path, ASSET.duration_s, ASSET.video, (), ())


class _StubDecoder:
    """Satisfies Decoder: one audio chunk and two frames, or a DecodeError from either."""

    def __init__(
        self,
        *,
        audio_error: DecodeError | None = None,
        frame_error: DecodeError | None = None,
        chunks: int = 1,
    ) -> None:
        self.audio_error = audio_error
        self.frame_error = frame_error
        self.chunks = chunks

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        if self.frame_error is not None:
            raise self.frame_error
        for t in (0.0, 1.0):
            yield Frame(t, np.full((48, 64, 3), 128, dtype=np.uint8))

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        if self.audio_error is not None:
            raise self.audio_error
        for _ in range(self.chunks):
            yield AudioChunk(0.0, BURSTS, SR)


def _run(
    decoder: _StubDecoder | None = None,
    *,
    asset: AssetInfo = ASSET,
    asr: FakeASR | None = None,
    captions: bool = True,
    beat: Callable[[], None] = lambda: None,
) -> tuple[AssetRecord, list[str]]:
    stages: list[str] = []
    backends = Backends(
        decoder or _StubDecoder(), FakeVAD(), asr or FakeASR(), FakeVLM() if captions else None
    )
    rec = index_asset(asset, stages.append, beat, backends=backends, cfg=Config())
    return rec, stages


def _cfg(
    backend: Literal["auto", "transformers", "none"], profile: Profile | None = None
) -> Config:
    return Config(vlm=VlmConfig(backend=backend), profile=profile)


def _problems(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_resolve_auto_with_vision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(pi, "vision_available", lambda: True)
    with caplog.at_level(logging.INFO):
        cfg = pi.resolve_config(_cfg("auto", Profile.CPU))
    assert cfg.vlm.backend == "transformers"
    assert _problems(caplog) == []


def test_resolve_auto_without_vision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(pi, "vision_available", lambda: False)
    with caplog.at_level(logging.INFO):
        cfg = pi.resolve_config(_cfg("auto", Profile.CPU))
    assert cfg.vlm.backend == "none"
    assert _problems(caplog) == ['captions off: install "tapesift[vision]"']


def test_resolve_explicit_transformers_without_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pi, "vision_available", lambda: False)
    with pytest.raises(ModelLoadError, match=r"tapesift\[vision\]"):
        pi.resolve_config(_cfg("transformers", Profile.CPU))


def test_resolve_none_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        cfg = pi.resolve_config(_cfg("none", Profile.CPU))
    assert cfg.vlm.backend == "none"
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert infos == ['captions off (vlm.backend = "none")']


def test_resolve_fills_profile() -> None:
    cfg = pi.resolve_config(_cfg("none"), probes=Probes(which=lambda _: None))
    assert cfg.profile is Profile.CPU


def test_both_stages_run() -> None:
    rec, _ = _run()
    assert len(rec.utterances) >= 1
    assert len(rec.captions) >= 2
    p = rec.provenance
    assert (p.asr, p.vlm, p.prompt) == ("fake:asr@" + Z, "fake:vlm@" + Z, "caption_v1")


def test_audio_stage_error_degrades() -> None:
    err = DecodeError(WarningCode.UNREADABLE, "x")
    rec, _ = _run(_StubDecoder(audio_error=err))
    assert rec.utterances == ()
    assert rec.provenance.asr is None
    assert err.warning in rec.warnings
    assert len(rec.captions) == 2


def test_caption_stage_error_degrades() -> None:
    err = DecodeError(WarningCode.UNSUPPORTED_CODEC, "y")
    rec, _ = _run(_StubDecoder(frame_error=err))
    assert rec.captions == ()
    assert (rec.provenance.vlm, rec.provenance.prompt) == (None, None)
    assert err.warning in rec.warnings
    assert len(rec.utterances) >= 1


def test_no_audio_means_no_asr() -> None:
    asr = FakeASR()
    rec, _ = _run(asset=ASSET_NO_AUDIO, asr=asr)
    assert rec.provenance.asr is None
    assert asr.calls == []


def test_captions_off() -> None:
    rec, _ = _run(captions=False)
    assert rec.captions == ()
    assert (rec.provenance.vlm, rec.provenance.prompt) == (None, None)
    assert rec.warnings == ()  # BURSTS gives the audio stage nothing to warn about
    assert len(rec.utterances) >= 1


def test_unexpected_error_propagates() -> None:
    class BoomASR(FakeASR):
        def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
            raise RuntimeError("x")

    stages: list[str] = []
    backends = Backends(_StubDecoder(), FakeVAD(), BoomASR(), FakeVLM())
    with pytest.raises(RuntimeError, match="x"):
        index_asset(ASSET, stages.append, lambda: None, backends=backends, cfg=Config())
    assert stages == ["asr"]


def test_stage_order() -> None:
    _, stages = _run()
    assert stages == ["asr", "vlm", "record"]


def test_decoder_items_beat() -> None:
    beats: list[int] = []
    _run(beat=lambda: beats.append(1))
    assert len(beats) >= 3  # one audio chunk and two frames


def test_pipeline_import_is_light() -> None:
    heavy = (
        "torch",
        "transformers",
        "ctranslate2",
        "faster_whisper",
        "lancedb",
        "pyarrow",
        "onnxruntime",
        "tokenizers",
        "huggingface_hub",
    )
    code = f"import sys, tapesift.pipeline.index; print(sorted(set({heavy!r}) & set(sys.modules)))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
