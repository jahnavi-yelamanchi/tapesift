"""Issue #26, row 17: probe, PyAV decode and the bundled Silero VAD through transcribe_asset, with a
fake ASR. Local (owner Q5): no model weights. The real ASR is in test_asr_models.py."""

from collections.abc import Sequence

import pytest
from conftest import FIXTURES

from tapesift.audio.stage import transcribe_asset
from tapesift.audio.vad import SileroVAD
from tapesift.config import AsrConfig, Config
from tapesift.media.decode import PyAVDecoder
from tapesift.media.probe import probe
from tapesift.media.types import AudioChunk
from tapesift.schema.records import AssetRecord, Provenance, Utterance
from tapesift.warning_codes import AssetWarning, WarningCode

# isort: split
from tests.fakes import FakeASR


@pytest.fixture(scope="module")
def vad() -> SileroVAD:
    return SileroVAD(Config())


class AllSpeechVAD:
    """Marks every chunk as speech from end to end."""

    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]:
        return [(chunk.start_s, chunk.start_s + len(chunk.samples) / chunk.sample_rate)]


class OvershootASR:
    """One utterance per piece, from the piece start to 0.6 s past the piece end."""

    id = "scripted:asr@" + "0" * 40

    def __init__(self) -> None:
        self.pieces: list[tuple[float, float]] = []

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        out: list[list[Utterance]] = []
        for c in chunks:
            end = c.start_s + len(c.samples) / c.sample_rate
            self.pieces.append((c.start_s, end))
            out.append([Utterance(c.start_s, end + 0.6, "hello", "en", 1.0, ())])
        return out


def test_low_speech_fixture(vad: SileroVAD) -> None:
    info, asr, sink = probe(FIXTURES / "silence.mp4"), FakeASR(), list[AssetWarning]()
    out = transcribe_asset(info, PyAVDecoder(), vad, asr, Config(), warn=sink.append)
    assert out == []
    assert sink == [
        AssetWarning(WarningCode.LOW_SPEECH, "audio stream 1: VAD found no speech in 4.0 s")
    ]
    assert asr.calls == []


@pytest.mark.parametrize("chunk_s", [pytest.param(600.0, id="600.0"), pytest.param(2.0, id="2.0")])
def test_speech_fixture(vad: SileroVAD, chunk_s: float) -> None:
    info, asr, sink = probe(FIXTURES / "speech.mp4"), FakeASR(), list[AssetWarning]()
    cfg = Config(asr=AsrConfig(batch_seconds=chunk_s))
    out = transcribe_asset(info, PyAVDecoder(), vad, asr, cfg, warn=sink.append)
    assert sink == []
    assert asr.calls == [1]  # the seams hold everything back: one piece, as at 600 s
    assert [u.start_s for u in out] == pytest.approx([0.00, 3.20], abs=0.02)
    assert [u.end_s for u in out] == pytest.approx([2.82, 6.60], abs=0.02)


def test_av_mismatch_clamped() -> None:
    info, asr, sink = probe(FIXTURES / "av_mismatch.mp4"), OvershootASR(), list[AssetWarning]()
    assert info.duration_s == pytest.approx(3.0, abs=0.05)  # 3 s video, 6 s audio
    out = transcribe_asset(info, PyAVDecoder(), AllSpeechVAD(), asr, Config(), warn=sink.append)
    assert out
    assert out[-1].end_s == pytest.approx(asr.pieces[-1][1], abs=1e-6)  # clamped to the piece end
    assert info.duration_s is not None
    assert out[-1].end_s <= info.duration_s
    AssetRecord(info, tuple(out), (), tuple(sink), Provenance("0.1.0", asr.id, None, None))
