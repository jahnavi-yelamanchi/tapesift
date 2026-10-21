"""M1 (#25) smoke: real probe and PyAVDecoder on fixtures, fakes for every model.
Spec: docs/specs/25-m1-interfaces.md, "Smoke tests"; rules R1 and R2 (clamp at the stage edge)."""

import pytest
from conftest import FIXTURES

# Each block below is its own isort section: the new interface modules do not exist yet, and ruff
# groups a missing module as third-party until they do. This order is valid before and after.
# isort: split
import tapesift
from tapesift.media.decode import PyAVDecoder
from tapesift.media.probe import probe
from tapesift.media.types import AssetInfo, AudioChunk

# isort: split
from tapesift.schema.records import (
    AssetRecord,
    Provenance,
    Utterance,
    Word,
    clamp_utterance,
)

# isort: split
from tests.fakes import FakeASR, FakeVAD

SPEECH_SPANS = [(0.00, 2.82), (3.20, 6.60)]


def _first_chunk(info: AssetInfo) -> AudioChunk:
    return next(PyAVDecoder().iter_audio(info, warn=[].append))


def _record(info: AssetInfo, utterances: list[Utterance]) -> AssetRecord:
    prov = Provenance(tapesift.__version__, FakeASR.id, None, None)
    return AssetRecord(info, tuple(utterances), (), (), prov)


@pytest.mark.parametrize(
    "name", ["speech.mp4", "silence.mp4", "music.m4a", "av_mismatch.mp4", "clean.mp4"]
)
def test_fake_vad_matches_fixture_labels(name: str) -> None:
    spans = FakeVAD().speech_spans(_first_chunk(probe(FIXTURES / name)))
    if name != "speech.mp4":
        assert spans == []
        return
    assert len(spans) == 2
    for (s, e), (want_s, want_e) in zip(spans, SPEECH_SPANS, strict=True):
        assert s == pytest.approx(want_s, abs=0.02)
        assert e == pytest.approx(want_e, abs=0.02)


def _overshot_speech() -> tuple[AssetInfo, AudioChunk, list[Utterance]]:
    info = probe(FIXTURES / "speech.mp4")
    chunk = _first_chunk(info)
    (utterances,) = FakeASR(overshoot_s=0.5).transcribe([chunk])
    return info, chunk, utterances


def test_whisper_overshoot_needs_clamp() -> None:
    info, _, utterances = _overshot_speech()
    assert info.duration_s == 7.0
    assert len(utterances) == 2
    assert utterances[1].end_s == pytest.approx(7.10, abs=0.02)
    with pytest.raises(ValueError):
        _record(info, utterances)


def test_whisper_overshoot_clamped_record_is_valid() -> None:
    info, chunk, utterances = _overshot_speech()
    assert info.duration_s is not None
    hi = min(chunk.start_s + len(chunk.samples) / chunk.sample_rate, info.duration_s)
    clamped = [c for u in utterances if (c := clamp_utterance(u, chunk.start_s, hi))]
    record = _record(info, clamped)
    assert len(record.utterances) == 2
    assert record.utterances[-1].end_s <= 7.0


def test_av_mismatch_utterance_clamped_to_duration() -> None:
    info = probe(FIXTURES / "av_mismatch.mp4")
    assert info.duration_s == pytest.approx(3.0)
    words = (Word("late", 2.5, 2.9), Word("words", 2.9, 3.04))
    u = Utterance(2.5, 3.04, "late words", "en", 0.9, words)
    with pytest.raises(ValueError):
        _record(info, [u])
    clamped = clamp_utterance(u, 0.0, 3.0)
    assert clamped is not None
    record = _record(info, [clamped])
    assert record.utterances[0].end_s == 3.0
    assert (record.utterances[0].words[-1].start_s, record.utterances[0].words[-1].end_s) == (
        2.9,
        3.0,
    )
