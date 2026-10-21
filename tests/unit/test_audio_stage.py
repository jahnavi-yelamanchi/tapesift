"""The audio stage (docs/specs/26-audio.md, rows 1-12): pure helpers, then transcribe_asset against
a scripted decoder, VAD and ASR. No real decode and no model weights (ADR 0008)."""

import logging
import math
import tracemalloc
from collections.abc import Callable, Iterable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from tapesift.audio.phantoms import PHANTOM_PHRASES, is_phantom_text
from tapesift.audio.stage import (
    MAX_CARRY_S,
    MIN_PIECE_S,
    covered_s,
    low_speech_detail,
    merge_spans,
    seam_cut,
    transcribe_asset,
)
from tapesift.audio.types import ASR, VAD
from tapesift.config import AsrConfig, Config
from tapesift.media.types import AssetInfo, AudioChunk, AudioStreamInfo, Decoder, Frame
from tapesift.schema.records import AssetRecord, Provenance, Utterance, Word
from tapesift.warning_codes import AssetWarning, WarningCode, WarningSink

# isort: split
from tests.fakes import FakeASR, FakeVAD

SR = 16_000
AID = "tsid1:" + "0" * 64
STREAM = AudioStreamInfo(1, "aac", None, True)
Span = tuple[float, float]


def _block() -> NDArray[np.float32]:
    """10 s: 18 x (0.3 s of 440 Hz at 0.3, then 0.2 s of zeros), then 1.0 s of zeros. The tones
    end at 8.8 s, so FakeVAD (which joins gaps under 0.3 s) gives one span (0.0, 8.8)."""
    tone = (0.3 * np.sin(2 * np.pi * 440 * np.arange(int(0.3 * SR)) / SR)).astype(np.float32)
    burst = np.concatenate([tone, np.zeros(int(0.2 * SR), dtype=np.float32)])
    return np.concatenate([np.tile(burst, 18), np.zeros(SR, dtype=np.float32)])


BLOCK = _block()
ZEROS_10 = np.zeros(10 * SR, dtype=np.float32)


def make_asset(
    duration_s: float | None, audio: tuple[AudioStreamInfo, ...] = (STREAM,)
) -> AssetInfo:
    return AssetInfo(AID, Path("talk.mp4"), duration_s, None, audio, ())


def make_cfg(**asr: Any) -> Config:
    return Config(asr=AsrConfig(**asr))


class ListDecoder:
    """Decoder over canned audio. `data` is either one sample array, sliced into `chunk_s` pieces
    from 0.0 on every call, or a list with one list of (start_s, samples) per call (the last list
    serves any later call). Chunks are created inline in `yield`, so nothing here pins them."""

    def __init__(
        self,
        data: NDArray[np.float32] | Sequence[Sequence[tuple[float, NDArray[np.float32]]]],
        warnings: Sequence[AssetWarning] = (),
    ) -> None:
        self.data = data
        self.warnings = tuple(warnings)
        self.calls: list[dict[str, Any]] = []

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        return iter(())

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        self.calls.append({"sample_rate": sample_rate, "track": track, "chunk_s": chunk_s})
        for w in self.warnings:
            warn(w)
        if isinstance(self.data, np.ndarray):
            step = round(chunk_s * sample_rate)
            for i in range(0, len(self.data), step):
                yield AudioChunk(i / sample_rate, self.data[i : i + step], sample_rate)
        else:
            for start_s, samples in self.data[min(len(self.calls), len(self.data)) - 1]:
                yield AudioChunk(start_s, samples, sample_rate)


class ScriptedVAD:
    """Global speech spans, clipped to each chunk it is asked about."""

    def __init__(self, spans: Iterable[Span]) -> None:
        self.spans = list(spans)
        self.calls = 0

    def speech_spans(self, chunk: AudioChunk) -> list[Span]:
        self.calls += 1
        lo = chunk.start_s
        hi = lo + len(chunk.samples) / chunk.sample_rate
        return [(max(a, lo), min(b, hi)) for a, b in self.spans if min(b, hi) > max(a, lo)]


class ScriptedASR:
    id = "scripted:asr@" + "0" * 40

    def __init__(self, fn: Callable[[AudioChunk], list[Utterance]]) -> None:
        self.fn = fn
        self.calls: list[tuple[float, float]] = []  # (piece.start_s, piece_end) per piece

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        out: list[list[Utterance]] = []
        for c in chunks:
            self.calls.append((c.start_s, c.start_s + len(c.samples) / c.sample_rate))
            out.append(self.fn(c))
        return out


def utt(start_s: float, end_s: float, text: str = "words here", *words: Word) -> Utterance:
    return Utterance(start_s, end_s, text, "en", 1.0, words)


def run(
    asset: AssetInfo,
    decoder: Decoder,
    vad: VAD,
    asr: ASR,
    cfg: Config | None = None,
) -> tuple[list[Utterance], list[AssetWarning]]:
    sink: list[AssetWarning] = []
    out = transcribe_asset(asset, decoder, vad, asr, cfg or Config(), warn=sink.append)
    return out, sink


def warnings_at(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


# ---- row 1: merge_spans, covered_s ----

_T = st.integers(min_value=0, max_value=64 * 100).map(lambda i: i / 64)  # exact in binary
_SPANS = st.lists(st.tuples(_T, _T), max_size=8)


@settings(deadline=None)
@given(spans=_SPANS)
def _prop_merge_spans(spans: list[Span]) -> None:
    join = 0.25
    out = merge_spans(spans, join)
    valid = [(a, b) for a, b in spans if b > a]
    assert all(a < b for a, b in out)
    assert all(nxt[0] - cur[1] >= join for cur, nxt in pairwise(out))
    assert all(any(a <= x and y <= b for a, b in out) for x, y in valid)
    assert {a for a, _ in out} <= {a for a, _ in valid}
    assert {b for _, b in out} <= {b for _, b in valid}
    assert merge_spans(reversed(spans), join) == out  # order does not matter
    assert merge_spans(out, join) == out  # idempotent


@settings(deadline=None)
@given(spans=_SPANS, cuts=st.tuples(_T, _T, _T).map(sorted))
def _prop_covered_s(spans: list[Span], cuts: list[float]) -> None:
    speech = merge_spans(spans, 0.25)
    a, b, c = cuts
    assert 0.0 <= covered_s(speech, a, c) <= c - a
    assert covered_s(speech, a, c) == pytest.approx(
        covered_s(speech, a, b) + covered_s(speech, b, c)
    )
    assert covered_s(speech, 0.0, math.inf) == pytest.approx(sum(y - x for x, y in speech))


def test_merge_spans() -> None:
    assert merge_spans([]) == []
    assert merge_spans([(2, 3), (0, 1)]) == [(0, 1), (2, 3)]
    assert merge_spans([(0, 2), (1, 3)]) == [(0, 3)]
    assert merge_spans([(0, 1), (1.25, 2)]) == [(0, 2)]
    assert merge_spans([(0, 1), (1.5, 2), (3, 3)]) == [(0, 1), (1.5, 2)]
    _prop_merge_spans()


def test_covered_s() -> None:
    assert covered_s([], 0, 10) == 0.0
    assert covered_s([(1, 2), (3, 5)], 0, 4) == 2.0
    assert covered_s([(1, 2), (3, 5)], 0.0, math.inf) == 3.0  # the stage's whole-file call
    _prop_covered_s()


# ---- row 2: seam_cut ----


@settings(deadline=None)
@given(
    spans=_SPANS,
    start=_T,
    length=st.integers(min_value=1, max_value=64 * 100).map(lambda i: i / 64),
)
def _prop_seam_cut(spans: list[Span], start: float, length: float) -> None:
    speech = merge_spans(spans)  # the default join, as the stage passes it
    end = start + length
    cut = seam_cut(start, end, speech)
    assert start <= cut <= end
    mids = [(b1 + a2) / 2 for (_, b1), (a2, _) in pairwise(speech)]
    ok = [m for m in mids if m - start >= MIN_PIECE_S and end - MAX_CARRY_S <= m < end]
    if not any(a <= end <= b for a, b in speech):
        assert cut == end  # rule 1: the buffer ends in silence
    elif ok:
        assert cut == pytest.approx(max(ok))  # rule 2: the latest usable gap midpoint
    elif end - start <= MAX_CARRY_S:
        assert cut == start  # rule 3: hold the whole buffer back
    else:
        assert cut == end  # rule 4: hard cut


@pytest.mark.parametrize(
    ("speech", "start", "end", "expected"),
    [
        pytest.param([(1, 3)], 0, 10, 10, id="end_in_silence"),
        pytest.param([(0, 5), (6, 12)], 0, 10, 5.5, id="gap_in_window"),
        pytest.param([(0, 12)], 0, 10, 0, id="short_held_back"),
        pytest.param([(0, 0.4), (0.6, 12)], 0, 10, 0, id="gap_too_close_to_start"),
        pytest.param([(0, 2), (3, 40)], 0, 38, 38, id="no_gap_long_hard_cut"),
    ],
)
def test_seam_cut(speech: list[Span], start: float, end: float, expected: float) -> None:
    assert seam_cut(start, end, speech) == expected
    _prop_seam_cut()


# ---- row 3: low_speech_detail ----


@settings(deadline=None)
@given(
    audio_s=st.floats(min_value=0.0, max_value=1e5),
    frac=st.floats(min_value=0.0, max_value=1.0),
    threshold=st.floats(min_value=0.0, max_value=1.0),
)
def _prop_low_speech_detail(audio_s: float, frac: float, threshold: float) -> None:
    speech_s = min(audio_s * frac, audio_s)
    d = low_speech_detail(1, speech_s, audio_s, threshold)
    if audio_s == 0:
        assert d == "audio stream 1: no audio samples decoded"
    elif speech_s == 0:
        assert d == f"audio stream 1: VAD found no speech in {audio_s:.1f} s"
    elif speech_s < 60.0 and speech_s / audio_s < threshold:
        assert d is not None
        assert d.startswith(f"audio stream 1: VAD speech {speech_s:.1f} s of {audio_s:.1f} s")
    else:
        assert d is None


def test_low_speech_detail() -> None:
    assert low_speech_detail(1, 0, 0, 0.05) == "audio stream 1: no audio samples decoded"
    assert low_speech_detail(1, 0, 4.0, 0.0) == "audio stream 1: VAD found no speech in 4.0 s"
    assert low_speech_detail(1, 0.0625, 1.0, 0.0625) is None  # exactly at the threshold: ASR runs
    assert low_speech_detail(1, 480.0, 10800.0, 0.05) is None  # floor: 60 s or more is kept
    assert low_speech_detail(1, 59.9, 10800.0, 0.05) == (
        "audio stream 1: VAD speech 59.9 s of 10800.0 s, ratio 0.006 < 0.05"
    )
    _prop_low_speech_detail()


# ---- rows 4-7: tracks, the gate, decode warnings ----


def test_no_audio() -> None:
    decoder, vad, asr = ListDecoder([]), ScriptedVAD([(0, 1)]), FakeASR()
    out, sink = run(make_asset(5.0, audio=()), decoder, vad, asr)
    assert out == []
    assert decoder.calls == []
    assert vad.calls == 0
    assert asr.calls == []
    assert sink == []


@pytest.mark.parametrize(
    ("span_end", "gated"),
    [pytest.param(0.03125, True, id="below"), pytest.param(0.125, False, id="above")],
)
def test_low_speech_gate(span_end: float, gated: bool) -> None:
    decoder = ListDecoder(np.zeros(SR, dtype=np.float32))
    asr = FakeASR()
    out, sink = run(
        make_asset(1.0),
        decoder,
        ScriptedVAD([(0, span_end)]),
        asr,
        make_cfg(vad_min_speech_ratio=0.0625),
    )
    if gated:
        assert out == []
        assert sink == [
            AssetWarning(
                WarningCode.LOW_SPEECH,
                "audio stream 1: VAD speech 0.0 s of 1.0 s, ratio 0.031 < 0.0625",
            )
        ]
        assert asr.calls == []
        assert len(decoder.calls) == 1
    else:
        assert sink == []
        assert asr.calls == [1]


def test_audio_track_out_of_range(caplog: pytest.LogCaptureFixture) -> None:
    streams = (AudioStreamInfo(1, "aac", "eng", True), AudioStreamInfo(2, "aac", "eng", False))
    decoder = ListDecoder(np.zeros(SR, dtype=np.float32))
    asr = FakeASR()
    with caplog.at_level(logging.INFO):
        out, sink = run(
            make_asset(1.0, audio=streams), decoder, FakeVAD(), asr, make_cfg(audio_track=5)
        )
    assert out == []
    assert decoder.calls
    assert all(c["track"] is None for c in decoder.calls)
    assert sink == [
        AssetWarning(WarningCode.LOW_SPEECH, "audio stream 1: VAD found no speech in 1.0 s")
    ]
    assert asr.calls == []
    assert warnings_at(caplog, logging.WARNING) == [
        "asr.audio_track 5 not in 0..1; using the default track"
    ]


def test_decode_warning_once() -> None:
    partial = AssetWarning(WarningCode.PARTIAL_DECODE, "audio stream 1: undecodable 0.50-1.00 s")
    decoder = ListDecoder(np.zeros(SR, dtype=np.float32), warnings=[partial])
    asr = FakeASR()
    _, sink = run(make_asset(1.0), decoder, ScriptedVAD([(0, 1)]), asr)
    assert len(decoder.calls) == 2  # both passes ran, both sent the warning
    assert asr.calls == [1]
    assert sink == [partial]


# ---- row 8: each span transcribed once across seams ----


@pytest.mark.parametrize("chunk_s", [1.0, 600.0])
def test_each_span_once(chunk_s: float) -> None:
    decoder = ListDecoder(np.concatenate([BLOCK, BLOCK]))
    out, sink = run(
        make_asset(20.0), decoder, FakeVAD(), FakeASR(), make_cfg(batch_seconds=chunk_s)
    )
    assert sink == []
    assert [c["chunk_s"] for c in decoder.calls] == [chunk_s, chunk_s]
    assert all(c["sample_rate"] == SR for c in decoder.calls)
    assert [u.text for u in out] == ["fake speech", "fake speech"]
    assert [u.start_s for u in out] == pytest.approx([0.0, 10.0], abs=0.02)
    assert [u.end_s for u in out] == pytest.approx([8.8, 18.8], abs=0.02)


# ---- rows 9-10: clamp and overlap ----


def test_clamp_inside_duration() -> None:
    asset = make_asset(9.0)
    asr = FakeASR(overshoot_s=0.5)
    out, sink = run(asset, ListDecoder(BLOCK[: 9 * SR]), FakeVAD(), asr)
    assert sink == []
    assert out
    assert out[-1].end_s == 9.0
    assert out[-1].words[-1].end_s == 9.0
    AssetRecord(asset, tuple(out), (), (), Provenance("0.1.0", FakeASR().id, None, None))


@settings(deadline=None, max_examples=40)
@given(
    items=st.lists(
        st.tuples(_T.filter(lambda t: t < 10), st.integers(0, 64 * 3).map(lambda i: i / 64)),
        max_size=6,
    )
)
def _prop_overlap_cap(items: list[Span]) -> None:
    given_utts = [utt(s, min(s + d, 10.9), "x") for s, d in sorted(items)]
    asset = make_asset(10.0)
    out, _ = run(
        asset,
        ListDecoder(ZEROS_10),
        ScriptedVAD([(0, 10)]),
        ScriptedASR(lambda piece: list(given_utts)),
    )
    assert [u.start_s for u in out] == sorted(u.start_s for u in out)
    assert all(0.0 <= u.start_s <= u.end_s <= 10.0 for u in out)
    assert all(a.end_s - b.start_s <= 0.1 + 1e-9 for a, b in pairwise(out))
    AssetRecord(asset, tuple(out), (), (), Provenance("0.1.0", ScriptedASR.id, None, None))


def test_overlap_cap() -> None:
    first = utt(0, 5, "first one", Word("first", 0, 2), Word("one", 2, 5))
    second = utt(4, 8, "second")
    out, _ = run(
        make_asset(10.0),
        ListDecoder(ZEROS_10),
        ScriptedVAD([(0, 10)]),
        ScriptedASR(lambda piece: [first, second]),
    )
    assert len(out) == 2
    assert (out[0].start_s, out[0].end_s) == (0.0, pytest.approx(4.1))
    assert out[0].words[0] == Word("first", 0, 2)
    assert (out[0].words[-1].w, out[0].words[-1].start_s) == ("one", 2.0)
    assert out[0].words[-1].end_s == pytest.approx(4.1)
    assert out[1] == second
    _prop_overlap_cap()


# ---- row 11: phantoms ----


@pytest.mark.parametrize(
    ("start_s", "end_s", "kept"),
    [
        pytest.param(1, 2, True, id="in_speech_kept"),
        pytest.param(5, 6, False, id="in_silence_dropped"),
    ],
)
def test_phantom(
    caplog: pytest.LogCaptureFixture, start_s: float, end_s: float, kept: bool
) -> None:
    said = utt(start_s, end_s, "Thanks for watching!")
    with caplog.at_level(logging.INFO):
        out, sink = run(
            make_asset(10.0),
            ListDecoder(ZEROS_10),
            ScriptedVAD([(0, 4)]),
            ScriptedASR(lambda piece: [said]),
        )
    assert sink == []
    infos = [m for m in warnings_at(caplog, logging.INFO) if "phantom" in m]
    if kept:
        assert out == [said]
        assert infos == []
    else:
        assert out == []
        assert infos == ['dropped phantom phrases: "thanks for watching" x1']


@settings(deadline=None)
@given(
    pad_l=st.text(alphabet=" \t\n", max_size=3),
    pad_r=st.text(alphabet=" \t\n", max_size=3),
    extra=st.text(alphabet="xyz", min_size=1, max_size=5),
)
def _prop_phantom_normalization(pad_l: str, pad_r: str, extra: str) -> None:
    for phrase in PHANTOM_PHRASES:
        assert is_phantom_text(pad_l + phrase.upper() + pad_r)
        assert not is_phantom_text(phrase + " " + extra)  # the WHOLE utterance must match


def test_is_phantom_text() -> None:
    assert is_phantom_text("Thanks for watching!")
    assert is_phantom_text("THANK YOU.")
    assert not is_phantom_text("Thank you for coming.")
    assert not is_phantom_text("")
    assert not is_phantom_text("Thanks for watching and see you")
    _prop_phantom_normalization()


# ---- row 12: M1 R8 memory bound (owner-required) ----


class TemplateDecoder:
    """n consecutive 600 s chunks, each a fresh copy of one template, created inline in `yield`."""

    def __init__(self, template: NDArray[np.float32], n: int) -> None:
        self.template = template
        self.n = n

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        return iter(())

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        for k in range(self.n):
            yield AudioChunk(k * 600.0, self.template.copy(), 16000)


@pytest.mark.slow
def test_streaming_memory_bound() -> None:
    template = np.tile(BLOCK, 60)  # 600 s, 38.4 MB, built before tracing
    c630 = AudioChunk(0.0, np.tile(BLOCK, 63), SR)  # 630 s: the biggest buffer the stage forms

    tracemalloc.start()
    FakeVAD().speech_spans(c630)
    FakeASR().transcribe([c630])
    _, fakes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    def peak(n: int) -> tuple[int, int]:
        asset = make_asset(n * 600.0)
        tracemalloc.start()
        try:
            out, _ = run(asset, TemplateDecoder(template, n), FakeVAD(), FakeASR())
            _, p = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return p, len(out)

    (p6, n6), (p12, n12) = peak(6), peak(12)
    report = f"fakes {fakes}, peak(6) {p6}, peak(12) {p12}"  # the PR quotes these
    logging.getLogger(__name__).info(report)
    assert p6 <= fakes + 80_640_000 + 4 * 2**20, report
    assert abs(p12 - p6) <= 0.10 * p6, report
    assert (n6, n12) == (60 * 6, 60 * 12)
