"""FasterWhisperASR without weights (docs/specs/26-audio.md, row 14): the pure helpers, the load
failure path on an empty directory, and the call protocol against a stub WhisperModel (ADR 0008)."""

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tapesift.audio.faster_whisper import (
    TRANSCRIBE_KWARGS,
    FasterWhisperASR,
    device_for,
    to_utterance,
)
from tapesift.config import ASR_MODELS, Config, ModelLoadError, Profile
from tapesift.media.types import AudioChunk

SR = 16_000
_T = st.integers(min_value=0, max_value=64 * 700).map(lambda i: i / 64)  # exact in binary


def _make(avg_logprob: float, text: str = "hi") -> Any:
    return to_utterance(
        0.0, 1.0, text, avg_logprob, [], lang="en", chunk_start_s=0.0, chunk_end_s=10.0
    )


@settings(deadline=None)
@given(
    start=_T,
    end=_T,
    chunk_start=_T,
    length=st.integers(min_value=1, max_value=64 * 700).map(lambda i: i / 64),
    words=st.lists(st.tuples(st.sampled_from(["a", " b", "  ", ""]), _T, _T), max_size=6),
)
def _prop_times_inside_chunk(
    start: float,
    end: float,
    chunk_start: float,
    length: float,
    words: list[tuple[str, float, float]],
) -> None:
    chunk_end = chunk_start + length
    u = to_utterance(
        start - 100,  # chunk-relative times may fall outside the chunk
        end - 100,
        "text",
        -1.0,
        [(w, s - 100, e - 100) for w, s, e in words],
        lang=None,
        chunk_start_s=chunk_start,
        chunk_end_s=chunk_end,
    )
    assert u is not None  # Utterance validates sorted words inside [start, end] itself
    assert chunk_start <= u.start_s <= u.end_s <= chunk_end + 1.0
    assert all(w.w == w.w.strip() and w.w for w in u.words)
    assert len(u.words) == sum(1 for w, _, _ in words if w.strip())


@settings(deadline=None)
@given(x=st.floats(min_value=-1e6, max_value=100.0, allow_nan=False, allow_infinity=False))
def _prop_conf_is_capped_exp(x: float) -> None:
    u = _make(x)
    assert u is not None
    assert u.conf == pytest.approx(min(1.0, math.exp(x)))


def test_to_utterance() -> None:
    u = to_utterance(
        1.0,
        2.0,
        " Hello there. ",
        -0.5,
        [(" Hello", 1.0, 1.4), (" there.", 1.4, 2.0)],
        lang="en",
        chunk_start_s=600.0,
        chunk_end_s=610.0,
    )
    assert u is not None
    assert (u.start_s, u.end_s, u.text, u.lang) == (601.0, 602.0, "Hello there.", "en")
    assert u.conf == pytest.approx(math.exp(-0.5))
    assert [(w.w, w.start_s, w.end_s) for w in u.words] == [
        ("Hello", 601.0, pytest.approx(601.4)),
        ("there.", pytest.approx(601.4), 602.0),
    ]
    # Whisper rounds a segment past the chunk: the start clamps to the chunk end, the end may
    # overshoot it by MAX_END_OVERSHOOT_S.
    late = to_utterance(
        10.5, 12.0, "late", -0.1, [], lang="en", chunk_start_s=600.0, chunk_end_s=610.0
    )
    assert late is not None
    assert (late.start_s, late.end_s) == (610.0, 611.0)
    # Blank text is dropped; blank words are dropped; words come out sorted.
    assert _make(-0.1, text="  \n") is None
    mixed = to_utterance(
        1.0,
        2.0,
        "a b",
        -0.1,
        [(" b", 1.5, 1.8), (" a", 1.0, 1.4), ("  ", 1.9, 1.95)],
        lang=None,
        chunk_start_s=0.0,
        chunk_end_s=10.0,
    )
    assert mixed is not None
    assert [w.w for w in mixed.words] == ["a", "b"]
    assert mixed.lang is None
    _prop_times_inside_chunk()


def test_conf() -> None:
    for logprob, conf in ((0.0, 1.0), (-math.inf, 0.0), (math.nan, 0.0), (math.inf, 0.0)):
        u = _make(logprob)
        assert u is not None
        assert u.conf == conf
    u = _make(3.0)  # exp(3) > 1 is capped
    assert u is not None
    assert u.conf == 1.0
    _prop_conf_is_capped_exp()


def test_load_failure_is_model_load_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tapesift.audio.faster_whisper.fetch_pin", lambda pin: tmp_path)
    with pytest.raises(ModelLoadError) as exc:
        FasterWhisperASR(Config())
    assert str(exc.value).startswith(
        "cannot load Systran/faster-whisper-small@536b0662742c: RuntimeError"
    )


def test_transcribe_with_stub_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, Any]] = []
    consumed: list[int] = []
    built: list[tuple[str, str, str]] = []

    class StubModel:
        def __init__(self, path: str, *, device: str, compute_type: str) -> None:
            built.append((path, device, compute_type))

        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, Any]:
            events.append(("transcribe", (audio, kwargs)))
            word = SimpleNamespace(start=0.5, end=0.7, word=" hi", probability=0.9)
            seg = SimpleNamespace(
                start=0.5, end=1.0, text=" hi", avg_logprob=-0.1, no_speech_prob=0.0, words=[word]
            )

            def segments() -> Any:  # a generator, like faster-whisper's lazy segments
                yield seg
                consumed.append(1)  # only reached if the caller drained it

            return segments(), SimpleNamespace(language="en")

    monkeypatch.setattr("tapesift.audio.faster_whisper.fetch_pin", lambda pin: tmp_path)
    monkeypatch.setattr("faster_whisper.WhisperModel", StubModel)
    monkeypatch.setattr("ctranslate2.set_random_seed", lambda seed: events.append(("seed", seed)))

    asr = FasterWhisperASR(Config())
    assert built == [(str(tmp_path), "cpu", "int8")]
    assert asr.id == ASR_MODELS["small"].id
    chunks = [AudioChunk(s, np.zeros(2 * SR, dtype=np.float32), SR) for s in (0.0, 600.0)]
    out = asr.transcribe(chunks)

    assert [e[0] for e in events] == ["seed", "transcribe", "seed", "transcribe"]
    assert [e[1] for e in events if e[0] == "seed"] == [0, 0]
    calls = [e[1] for e in events if e[0] == "transcribe"]
    assert all(kwargs == TRANSCRIBE_KWARGS for _, kwargs in calls)
    assert [audio is c.samples for (audio, _), c in zip(calls, chunks, strict=True)] == [True, True]
    assert consumed == [1, 1]
    assert [[u.start_s for u in per_chunk] for per_chunk in out] == [[0.5], [600.5]]
    assert [u.text for per_chunk in out for u in per_chunk] == ["hi", "hi"]
    assert [u.lang for per_chunk in out for u in per_chunk] == ["en", "en"]

    assert [device_for(p) for p in (None, Profile.CPU, Profile.GPU, Profile.SERVER)] == [
        "cpu",
        "cpu",
        "cuda",
        "cuda",
    ]


def test_non_speech_segments_dropped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Measured in the models job (runs 39598237998, 39598594019): a steady tone decodes to "Beep"
    # with no_speech_prob 0.71-0.74 and avg_logprob -0.99..-1.0, right at faster-whisper's own
    # -1.0 skip bar, so it flips by runner CPU. speech.mp4 measures 0.019 and -0.32.
    rows = [("Beep", 0.712, -0.9985), ("Beep", 0.735, -0.9925), ("hi", 0.019, -0.3198)]

    class StubModel:
        def __init__(self, path: str, *, device: str, compute_type: str) -> None:
            pass

        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, Any]:
            segs = [
                SimpleNamespace(
                    start=0.0, end=1.0, text=t, avg_logprob=lp, no_speech_prob=ns, words=[]
                )
                for t, ns, lp in rows
            ]
            return iter(segs), SimpleNamespace(language="en")

    monkeypatch.setattr("tapesift.audio.faster_whisper.fetch_pin", lambda pin: tmp_path)
    monkeypatch.setattr("faster_whisper.WhisperModel", StubModel)
    monkeypatch.setattr("ctranslate2.set_random_seed", lambda seed: None)
    chunk = AudioChunk(0.0, np.zeros(2 * SR, dtype=np.float32), SR)
    (out,) = FasterWhisperASR(Config()).transcribe([chunk])
    assert [u.text for u in out] == ["hi"]
