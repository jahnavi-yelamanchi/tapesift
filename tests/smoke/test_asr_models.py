"""Issue #26, row 20: the real pinned faster-whisper model and Silero, end to end. Runs only in the
CI `models` job (owner Q4); never on the laptop (ADR 0008)."""

import logging
from collections.abc import Sequence
from typing import Any

import pytest
from conftest import FIXTURES

from tapesift.audio.faster_whisper import FasterWhisperASR
from tapesift.audio.stage import transcribe_asset
from tapesift.audio.types import ASR
from tapesift.audio.vad import SileroVAD
from tapesift.config import AsrConfig, Config
from tapesift.eval.wer import wer
from tapesift.media.decode import PyAVDecoder
from tapesift.media.probe import probe
from tapesift.media.types import AudioChunk
from tapesift.schema.records import Utterance
from tapesift.warning_codes import AssetWarning, WarningCode

pytestmark = pytest.mark.model

log = logging.getLogger(__name__)
MAX_WER = 0.20  # at most 3 of the 15 words wrong


class CountingASR:
    def __init__(self, inner: ASR) -> None:
        self.inner = inner
        self.calls = 0

    @property
    def id(self) -> str:
        return self.inner.id

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        self.calls += 1
        return self.inner.transcribe(chunks)


@pytest.fixture(scope="module")
def asr() -> FasterWhisperASR:
    return FasterWhisperASR(Config())


@pytest.fixture(scope="module")
def vad() -> SileroVAD:
    return SileroVAD(Config())


def _transcribe(
    asr: ASR, vad: SileroVAD, name: str, cfg: Config
) -> tuple[list[Utterance], list[AssetWarning]]:
    sink: list[AssetWarning] = []
    out = transcribe_asset(probe(FIXTURES / name), PyAVDecoder(), vad, asr, cfg, warn=sink.append)
    return out, sink


def _check_speech(
    asr: ASR, vad: SileroVAD, manifest: Any, cfg: Config, chunk_s: str
) -> list[Utterance]:
    transcript: str = next(e for e in manifest["fixtures"] if e["name"] == "speech.mp4")[
        "transcript"
    ]
    out, sink = _transcribe(asr, vad, "speech.mp4", cfg)
    score = wer(transcript, " ".join(u.text for u in out))
    log.info("speech.mp4 WER chunk_s=%s: %.3f", chunk_s, score)
    assert sink == []
    assert score <= MAX_WER, f"WER {score:.3f}: {' '.join(u.text for u in out)!r}"
    assert all(u.lang == "en" for u in out)
    return out


def test_low_speech_real(asr: FasterWhisperASR, vad: SileroVAD) -> None:
    counting = CountingASR(asr)
    out, sink = _transcribe(counting, vad, "silence.mp4", Config())
    assert out == []
    assert sink == [
        AssetWarning(WarningCode.LOW_SPEECH, "audio stream 1: VAD found no speech in 4.0 s")
    ]
    assert counting.calls == 0


def test_speech_wer(asr: FasterWhisperASR, vad: SileroVAD, manifest: Any) -> None:
    first = _check_speech(asr, vad, manifest, Config(), "600")
    assert _transcribe(asr, vad, "speech.mp4", Config())[0] == first  # seeded: same output twice


def test_speech_wer_small_chunks(asr: FasterWhisperASR, vad: SileroVAD, manifest: Any) -> None:
    cfg = Config(asr=AsrConfig(batch_seconds=2.0))
    _check_speech(asr, vad, manifest, cfg, "2.0")
