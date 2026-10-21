"""E3: one asset's audio to Utterances (docs/specs/26-audio.md S1-S8; M1 R2, R8)."""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from itertools import pairwise
from typing import Final

import numpy as np

from tapesift.audio.phantoms import MAX_SPEECH_SHARE, is_phantom_text
from tapesift.audio.types import ASR, VAD
from tapesift.config import Config
from tapesift.eval.wer import normalize
from tapesift.media.types import AssetInfo, AudioChunk, Decoder
from tapesift.schema.records import Utterance, clamp_utterance
from tapesift.warning_codes import AssetWarning, WarningCode, WarningSink

log = logging.getLogger(__name__)

SAMPLE_RATE: Final = 16_000
MAX_CARRY_S: Final = 30.0  # longest tail held back for the next chunk at a seam (S2)
MIN_PIECE_S: Final = 1.0  # a seam cut leaves at least this much audio before it (S2)
SPAN_JOIN_S: Final = 0.3  # VAD spans with a smaller gap are one span; absorbs chunk-edge artifacts
KEEP_SPEECH_S: Final = 60.0  # never LOW_SPEECH with at least this much VAD speech (card 3)
MAX_OVERLAP_S: Final = 0.1  # consecutive utterances overlap by at most this (M1)
CLAMP_WARN_S: Final = 0.5  # a clamp moving a time by more than this logs one WARNING (M1 R2)

Span = tuple[float, float]


def merge_spans(spans: Iterable[Span], join_s: float = SPAN_JOIN_S) -> list[Span]:
    """Pure. Sorted union of the spans with b > a; spans whose gap (next a - current b) is below
    join_s, overlaps and touches included, become one."""
    out: list[Span] = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if out and a - out[-1][1] < join_s:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def covered_s(speech: Sequence[Span], start_s: float, end_s: float) -> float:
    """Pure. Seconds of [start_s, end_s] inside the merged spans `speech`."""
    return sum(max(0.0, min(b, end_s) - max(a, start_s)) for a, b in speech)


def low_speech_detail(index: int, speech_s: float, audio_s: float, threshold: float) -> str | None:
    """Pure (S3). The LOW_SPEECH detail, or None to run ASR:
    audio_s == 0: f"audio stream {index}: no audio samples decoded";
    speech_s == 0: f"audio stream {index}: VAD found no speech in {audio_s:.1f} s";
    speech_s < KEEP_SPEECH_S and speech_s / audio_s < threshold:
      f"audio stream {index}: VAD speech {speech_s:.1f} s of {audio_s:.1f} s, ratio {ratio:.3f} < {threshold:g}";
    else None."""  # noqa: E501
    if audio_s == 0:
        return f"audio stream {index}: no audio samples decoded"
    if speech_s == 0:
        return f"audio stream {index}: VAD found no speech in {audio_s:.1f} s"
    ratio = speech_s / audio_s
    if speech_s < KEEP_SPEECH_S and ratio < threshold:
        return (
            f"audio stream {index}: VAD speech {speech_s:.1f} s of {audio_s:.1f} s, "
            f"ratio {ratio:.3f} < {threshold:g}"
        )
    return None


def seam_cut(
    start_s: float, end_s: float, speech: Sequence[Span], max_carry_s: float = MAX_CARRY_S
) -> float:
    """Pure (S2). Where to cut the buffer [start_s, end_s); `speech` is merge_spans output.
    1. end_s is in silence (no span with a <= end_s <= b): end_s.
    2. Else the latest gap midpoint m = (b_i + a_{i+1}) / 2 with m - start_s >= MIN_PIECE_S,
       m < end_s and m >= end_s - max_carry_s.
    3. Else start_s, when end_s - start_s <= max_carry_s (hold the whole buffer back).
    4. Else end_s: a hard cut (no gap in the last max_carry_s seconds of a longer buffer)."""
    # ponytail: rule 4 may split one word inside 30 s+ of gapless speech; upgrade: cut at the
    # quietest 50 ms frame of the last 30 s (#13 r2 design, see Later).
    if not any(a <= end_s <= b for a, b in speech):
        return end_s
    for (_, b), (a, _) in reversed(list(pairwise(speech))):
        m = (b + a) / 2
        if m < end_s and m - start_s >= MIN_PIECE_S and m >= end_s - max_carry_s:
            return m
    return start_s if end_s - start_s <= max_carry_s else end_s


def _vad_pass(
    decoder: Decoder, asset: AssetInfo, vad: VAD, cfg: Config, track: int | None, sink: WarningSink
) -> tuple[list[Span], int]:
    """Pass 1: VAD spans and total sample count. A function so no chunk outlives the pass."""
    spans: list[Span] = []
    n = 0
    for c in decoder.iter_audio(
        asset, SAMPLE_RATE, track=track, chunk_s=cfg.asr.batch_seconds, warn=sink
    ):
        spans.extend(vad.speech_spans(c))
        n += len(c.samples)
        del c  # drop it before the decoder builds the next chunk: one chunk live at a time
    return spans, n


def _end(c: AudioChunk) -> float:
    return c.start_s + len(c.samples) / SAMPLE_RATE


def _join(old: AudioChunk | None, c: AudioChunk, k: int) -> AudioChunk:
    """Owned chunk `old ++ c[:k]` (AudioChunk copies the view when old is None)."""
    body = c.samples[:k]
    if old is None:
        return AudioChunk(c.start_s, body, SAMPLE_RATE)
    return AudioChunk(old.start_s, np.concatenate([old.samples, body]), SAMPLE_RATE)


def _pieces(
    chunks: Iterable[AudioChunk], speech: Sequence[Span], count: list[int]
) -> Iterator[AudioChunk]:
    """S2: yields the pieces to send to ASR (those with VAD speech), cut in VAD silence. Pieces
    never overlap. The consumer must drop each piece before asking for the next one."""
    carry: AudioChunk | None = None

    def worth_sending(p: AudioChunk) -> bool:
        return covered_s(speech, p.start_s, _end(p)) > 0

    for c in chunks:
        count[0] += len(c.samples)
        if carry is not None and abs(c.start_s - _end(carry)) > 0.5 / SAMPLE_RATE:
            if worth_sending(carry):  # run break: flush the carry on its own
                yield carry
            carry = None
        n = len(c.samples)
        buf_start = carry.start_s if carry is not None else c.start_s
        n_old = len(carry.samples) if carry is not None else 0
        cut = seam_cut(buf_start, c.start_s + n / SAMPLE_RATE, speech)
        kb = math.floor((cut - buf_start) * SAMPLE_RATE + 0.5)
        old, piece, carry = carry, None, None
        if kb < max(n_old, 1):  # hold everything back (a cut inside the carry cannot happen)
            carry = _join(old, c, n)
        else:
            k = min(kb - n_old, n)
            if k == n:
                piece = c if old is None else _join(old, c, n)
            else:
                piece = old if k == 0 else _join(old, c, k)
                carry = AudioChunk(c.start_s + k / SAMPLE_RATE, c.samples[k:].copy(), SAMPLE_RATE)
        if piece is not None and worth_sending(piece):
            yield piece
        del c, piece, old
    if carry is not None and worth_sending(carry):
        yield carry


def transcribe_asset(
    asset: AssetInfo, decoder: Decoder, vad: VAD, asr: ASR, cfg: Config, *, warn: WarningSink
) -> list[Utterance]:
    """R8. Sorted by start_s; consecutive utterances overlap by at most 0.1 s; every time inside
    [0, duration_s] (clamped, R2). [] when asset.audio is empty. Speech ratio from vad below
    cfg.asr.vad_min_speech_ratio: [] and LOW_SPEECH via warn, and asr.transcribe is never called.
    Track: cfg.asr.audio_track, else the default. StageError (e.g. DecodeError) propagates."""
    if not asset.audio:
        return []
    extra = {"asset_id": asset.id, "stage": "asr"}
    track = cfg.asr.audio_track
    if track is not None and not 0 <= track < len(asset.audio):
        log.warning(
            "asr.audio_track %d not in 0..%d; using the default track",
            track,
            len(asset.audio) - 1,
            extra=extra,
        )
        track = None
    stream = asset.audio[track] if track is not None else asset.default_audio
    assert stream is not None  # noqa: S101 - asset.audio is non-empty

    seen: set[AssetWarning] = set()

    def sink1(w: AssetWarning) -> None:
        seen.add(w)
        warn(w)

    def sink2(w: AssetWarning) -> None:
        if w not in seen:
            warn(w)

    spans, n1 = _vad_pass(decoder, asset, vad, cfg, track, sink1)
    speech = merge_spans(spans)
    detail = low_speech_detail(
        stream.index,
        covered_s(speech, 0.0, math.inf),
        n1 / SAMPLE_RATE,
        cfg.asr.vad_min_speech_ratio,
    )
    if detail is not None:
        warn(AssetWarning(WarningCode.LOW_SPEECH, detail))
        return []

    count = [0]
    out: list[Utterance] = []
    max_shift = 0.0
    chunks = decoder.iter_audio(
        asset, SAMPLE_RATE, track=track, chunk_s=cfg.asr.batch_seconds, warn=sink2
    )
    for piece in _pieces(chunks, speech, count):
        lo, hi = piece.start_s, _end(piece)
        if asset.duration_s is not None:
            hi = min(hi, asset.duration_s)
        (utterances,) = asr.transcribe([piece])
        del piece
        for u in utterances:
            if hi < lo or (cu := clamp_utterance(u, lo, hi)) is None:
                continue
            max_shift = max(max_shift, abs(cu.start_s - u.start_s), abs(cu.end_s - u.end_s))
            out.append(cu)
    if count[0] != n1:
        log.warning(
            "audio decode differed between passes: %d vs %d samples", n1, count[0], extra=extra
        )
    if max_shift > CLAMP_WARN_S:
        log.warning("ASR times moved up to %.2f s by clamping", max_shift, extra=extra)

    out.sort(key=lambda u: u.start_s)
    out = _drop_phantoms(out, speech, extra)
    for i in range(len(out) - 1):
        capped = clamp_utterance(out[i], out[i].start_s, out[i + 1].start_s + MAX_OVERLAP_S)
        if capped is not None and out[i].end_s > capped.end_s:
            out[i] = capped
    return out


def _drop_phantoms(
    utterances: list[Utterance], speech: Sequence[Span], extra: dict[str, str]
) -> list[Utterance]:
    """S5: phantom phrases where VAD heard (almost) no speech."""
    kept: list[Utterance] = []
    dropped: Counter[str] = Counter()
    for u in utterances:
        length = u.end_s - u.start_s
        if is_phantom_text(u.text) and covered_s(speech, u.start_s, u.end_s) <= (
            MAX_SPEECH_SHARE * length
        ):
            dropped[normalize(u.text)] += 1
        else:
            kept.append(u)
    if dropped:
        listed = ", ".join(f'"{t}" x{n}' for t, n in dropped.items())
        log.info("dropped phantom phrases: %s", listed, extra=extra)
    return kept
