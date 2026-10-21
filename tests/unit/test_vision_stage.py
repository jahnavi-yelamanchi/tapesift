"""Issue #27: tapesift.vision.stage.caption_asset (docs/specs/27-captions.md, Acceptance 1-9).
Stub decoder and stub VLMs; FakeVLM from tests.fakes. No real model, no torch (ADR 0008)."""

import logging
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest

from tapesift.config import Config, VlmConfig
from tapesift.media.decode import PyAVDecoder
from tapesift.media.probe import probe
from tapesift.media.types import AssetInfo, AudioChunk, Frame, VideoInfo
from tapesift.schema.records import Caption
from tapesift.warning_codes import AssetWarning, WarningCode, WarningSink

# Each block below is its own isort section: the new module does not exist yet, and ruff groups a
# missing module as third-party until it does. This order is valid before and after.
# isort: split
from tapesift.vision.stage import caption_asset

# isort: split
from tests.fakes import FakeVLM

FIXTURES = Path(__file__).parents[1] / "fixtures"
LOGGER = "tapesift.vision.stage"

STUB = AssetInfo(
    "tsid1:" + "0" * 64, Path("x.mp4"), 30.0, VideoInfo(0, "h264", 4, 4, 25.0, False, 0), (), ()
)


class StubDecoder:
    """Yields Frame(float(i), zeros) for i in range(n) and records every_s."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.every_s: list[float | None] = []

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        self.every_s.append(every_s)
        for i in range(self.n):
            yield Frame(float(i), np.zeros((4, 4, 3), np.uint8))

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        raise AssertionError("caption_asset must not decode audio")


class RecordingVLM:
    """Local stub: `media` maps frame t_s to media_text; `shift` offsets every returned t_s;
    `drop` removes captions from the end; `error` is raised instead of captioning."""

    id = "fake:vlm@" + "0" * 40

    def __init__(
        self,
        *,
        media: dict[float, tuple[str, ...]] | None = None,
        text: str = "a frame",
        shift: float = 0.0,
        drop: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.media = media or {}
        self.text = text
        self.shift = shift
        self.drop = drop
        self.error = error
        self.calls: list[int] = []

    def caption(self, frames: Sequence[Frame], prompt_id: str) -> list[Caption]:
        self.calls.append(len(frames))
        if self.error is not None:
            raise self.error
        caps = [
            Caption(f.t_s + self.shift, self.text, None, self.media.get(f.t_s, ())) for f in frames
        ]
        return caps[: len(caps) - self.drop]


class PromptSpyVLM(FakeVLM):
    def __init__(self) -> None:
        super().__init__()
        self.prompt_ids: list[str] = []

    def caption(self, frames: Sequence[Frame], prompt_id: str) -> list[Caption]:
        self.prompt_ids.append(prompt_id)
        return super().caption(frames, prompt_id)


def _ignore(_w: AssetWarning) -> None:
    return None


def test_clean_one_caption_per_frame() -> None:
    asset = probe(FIXTURES / "clean.mp4")
    expected = [f.t_s for f in PyAVDecoder().iter_frames(asset, 1.0, warn=_ignore)]
    assert len(expected) > 0
    sink: list[AssetWarning] = []
    caps = caption_asset(asset, PyAVDecoder(), FakeVLM(), Config(), warn=sink.append)
    assert [c.t_s for c in caps] == expected
    assert sink == []


@pytest.mark.parametrize(
    ("max_batch", "calls"), [(3, [3] * 6 + [2]), (None, [8, 8, 4])], ids=["3", "default"]
)
def test_batches_never_exceed_max_batch(max_batch: int | None, calls: list[int]) -> None:
    decoder, vlm = StubDecoder(20), PromptSpyVLM()
    cfg = Config(vlm=VlmConfig(max_batch=max_batch))
    caps = caption_asset(STUB, decoder, vlm, cfg, warn=_ignore)
    assert vlm.calls == calls
    assert [c.t_s for c in caps] == [float(i) for i in range(20)]
    assert vlm.prompt_ids == ["caption_v1"] * len(calls)
    assert decoder.every_s == [1.0]


def test_no_video_returns_empty() -> None:
    audio_only = AssetInfo(STUB.id, STUB.path, 30.0, None, (), ())
    decoder, vlm = StubDecoder(5), FakeVLM()
    assert caption_asset(audio_only, decoder, vlm, Config(), warn=_ignore) == []
    assert decoder.every_s == []
    assert vlm.calls == []


def test_no_frames_no_backend_call(caplog: pytest.LogCaptureFixture) -> None:
    vlm = FakeVLM()
    sink: list[AssetWarning] = []
    with caplog.at_level(logging.INFO, logger=LOGGER):
        caps = caption_asset(STUB, StubDecoder(0), vlm, Config(), warn=sink.append)
    assert caps == []
    assert vlm.calls == []
    assert sink == []
    infos = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]
    assert [r.getMessage() for r in infos] == ["captioned 0 frames"]


def test_backend_exception_propagates() -> None:
    boom = RuntimeError("boom")
    sink: list[AssetWarning] = []
    with pytest.raises(RuntimeError) as exc:
        caption_asset(STUB, StubDecoder(3), RecordingVLM(error=boom), Config(), warn=sink.append)
    assert exc.value is boom
    assert sink == []


def test_media_text_warns_once() -> None:
    media = {1.0: ("BUY NOW",), 3.0: ("BUY NOW",)}
    sink: list[AssetWarning] = []
    caps = caption_asset(
        STUB, StubDecoder(4), RecordingVLM(media=media), Config(), warn=sink.append
    )
    assert len(caps) == 4
    assert sink == [
        AssetWarning(
            WarningCode.MEDIA_TEXT,
            "on-screen text in 2 of 4 sampled frames; stored as untrusted media_text",
        )
    ]


def test_bad_backend_output_rejected() -> None:
    with pytest.raises(ValueError, match=r"VLM returned 1 captions for 2 frames"):
        caption_asset(STUB, StubDecoder(2), RecordingVLM(drop=1), Config(), warn=_ignore)
    with pytest.raises(ValueError, match=r"differs from its frame"):
        caption_asset(STUB, StubDecoder(2), RecordingVLM(shift=0.5), Config(), warn=_ignore)


def test_logs_counts_not_text(caplog: pytest.LogCaptureFixture) -> None:
    vlm = RecordingVLM(
        text="SECRET-CAPTION", media={0.0: ("SECRET-WORDS",), 1.0: ("SECRET-WORDS",)}
    )
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        caption_asset(STUB, StubDecoder(2), vlm, Config(), warn=_ignore)
    records = [r for r in caplog.records if r.name == LOGGER]
    infos = [r for r in records if r.levelno == logging.INFO]
    assert len(infos) == 1
    assert re.fullmatch(
        r"captioned 2 frames in 1 batches, \d+\.\d\d s/frame", infos[0].getMessage()
    )
    assert getattr(infos[0], "asset_id", None) == STUB.id
    for r in records:
        assert "SECRET" not in r.getMessage()
        assert "SECRET" not in repr(r.__dict__)


def test_vision_modules_import_no_backends() -> None:
    code = (
        "import sys, tapesift.vision.stage, tapesift.vision.prompts, "
        "tapesift.vision.transformers_vlm; "
        "print(sorted({'torch', 'transformers', 'PIL', 'huggingface_hub', 'av'} "
        "& set(sys.modules)))"
    )
    run = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "[]"
