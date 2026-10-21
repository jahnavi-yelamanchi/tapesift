"""FasterWhisperASR: ASR_MODELS[cfg.asr.model] through tapesift.hub.fetch_pin (M1 R4).
faster_whisper and ctranslate2 are imported inside __init__ only (R6)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any, Final, Literal, cast

from tapesift.config import ASR_MODELS, Config, ModelLoadError, Profile
from tapesift.hub import fetch_pin  # tests patch tapesift.audio.faster_whisper.fetch_pin
from tapesift.media.types import AudioChunk
from tapesift.schema.records import Utterance, Word

MAX_END_OVERSHOOT_S: Final = 1.0  # M1 ASR contract
SEED: Final = 0  # ctranslate2.set_random_seed(SEED) before every model.transcribe (spec 737)
TRANSCRIBE_KWARGS: Final = {"language": None, "word_timestamps": True, "vad_filter": False}
"""Everything else is a faster-whisper 1.2.1 default, including the temperature fallback.
language None: Whisper detects per call and the utterance records it (ADR 0010).
vad_filter off: the stage's VAD is the only detector (M1 R8)."""


NO_SPEECH_MAX: Final = 0.6  # faster-whisper's own no_speech_threshold
NO_SPEECH_LOGPROB_MAX: Final = -0.5
"""A segment is dropped as non-speech when Whisper's no_speech_prob exceeds NO_SPEECH_MAX and its
avg_logprob is below NO_SPEECH_LOGPROB_MAX. faster-whisper applies the same rule at logprob -1.0,
but a steady tone decodes to "Beep" at no_speech_prob 0.71-0.74, avg_logprob -0.99..-1.0, so the
result flips with the runner's CPU. Measured in the models job: tone 0.71-0.74 / -0.99..-1.0,
zeros 0.85-0.88 / -0.94, speech.mp4 0.019 / -0.32. It is a post-filter, so decoding (and its
temperature fallback) is untouched."""


def is_non_speech(no_speech_prob: float, avg_logprob: float) -> bool:
    """Pure. True for a segment Whisper itself says is not speech (see NO_SPEECH_MAX)."""
    return no_speech_prob > NO_SPEECH_MAX and avg_logprob < NO_SPEECH_LOGPROB_MAX


def device_for(profile: Profile | None) -> Literal["cpu", "cuda"]:
    """Pure. "cuda" for GPU and SERVER, else "cpu" (None counts as cpu)."""
    return "cuda" if profile in (Profile.GPU, Profile.SERVER) else "cpu"


def _clamp(t: float, a: float, b: float) -> float:
    return min(max(t, a), b)


def to_utterance(
    start: float,
    end: float,
    text: str,
    avg_logprob: float,
    words: Sequence[tuple[str, float, float]],
    *,
    lang: str | None,
    chunk_start_s: float,
    chunk_end_s: float,
) -> Utterance | None:
    """Pure. One segment (chunk-relative times) to an Utterance on the container clock; None when
    text.strip() is empty. With c(t, a, b) = min(max(t, a), b):
    s = c(start + chunk_start_s, chunk_start_s, chunk_end_s);
    e = c(end + chunk_start_s, s, chunk_end_s + MAX_END_OVERSHOOT_S);
    conf = min(1.0, exp(avg_logprob)), or 0.0 when avg_logprob is not finite;
    words = (w.strip(), ws = c(w_start + chunk_start_s, s, e), c(w_end + chunk_start_s, ws, e)),
    blank words dropped, sorted by ws; text = text.strip()."""
    text = text.strip()
    if not text:
        return None
    s = _clamp(start + chunk_start_s, chunk_start_s, chunk_end_s)
    e = _clamp(end + chunk_start_s, s, chunk_end_s + MAX_END_OVERSHOOT_S)
    conf = min(1.0, math.exp(avg_logprob)) if math.isfinite(avg_logprob) else 0.0
    out: list[Word] = []
    for w, w_start, w_end in words:
        if w.strip():
            ws = _clamp(w_start + chunk_start_s, s, e)
            out.append(Word(w.strip(), ws, _clamp(w_end + chunk_start_s, ws, e)))
    out.sort(key=lambda w: w.start_s)
    return Utterance(s, e, text, lang, conf, tuple(out))


class FasterWhisperASR:
    def __init__(self, cfg: Config) -> None:
        """pin = ASR_MODELS[cfg.asr.model]; d = fetch_pin(pin) (ModelLoadError passes through);
        WhisperModel(str(d), device=device_for(cfg.profile), compute_type=cfg.asr.compute_type).
        Any exception from WhisperModel becomes
        ModelLoadError(f"cannot load {pin.repo}@{pin.revision[:12]}: {type(e).__name__}: {e}")."""
        self._pin = ASR_MODELS[cfg.asr.model]
        d = fetch_pin(self._pin)
        try:
            import ctranslate2  # pyright: ignore[reportMissingTypeStubs]
            import faster_whisper  # pyright: ignore[reportMissingTypeStubs]

            self._ct2: Any = ctranslate2
            self._model: Any = faster_whisper.WhisperModel(
                str(d), device=device_for(cfg.profile), compute_type=cfg.asr.compute_type
            )
        except Exception as e:
            pin = self._pin
            raise ModelLoadError(
                f"cannot load {pin.repo}@{pin.revision[:12]}: {type(e).__name__}: {e}"
            ) from e

    @property
    def id(self) -> str:
        """ASR_MODELS[cfg.asr.model].id."""
        return self._pin.id

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        """M1 ASR. Per chunk: set_random_seed(SEED); model.transcribe(chunk.samples,
        **TRANSCRIBE_KWARGS), the generator consumed; each segment through to_utterance with
        lang=info.language and the chunk's bounds; None dropped. Exceptions propagate (R5)."""
        result: list[list[Utterance]] = []
        for chunk in chunks:
            chunk_end = chunk.start_s + len(chunk.samples) / chunk.sample_rate
            self._ct2.set_random_seed(SEED)
            segments: Iterable[Any]
            segments, info = self._model.transcribe(chunk.samples, **TRANSCRIBE_KWARGS)
            lang = cast("str | None", info.language)
            utterances: list[Utterance] = []
            for seg in segments:
                if is_non_speech(seg.no_speech_prob, seg.avg_logprob):
                    continue
                words = [
                    cast("tuple[str, float, float]", (w.word, w.start, w.end))
                    for w in cast("list[Any]", seg.words or [])
                ]
                u = to_utterance(
                    seg.start,
                    seg.end,
                    seg.text,
                    seg.avg_logprob,
                    words,
                    lang=lang,
                    chunk_start_s=chunk.start_s,
                    chunk_end_s=chunk_end,
                )
                if u is not None:
                    utterances.append(u)
            result.append(utterances)
        return result
