"""CPU decode with PyAV (E2): M0's Decoder. docs/specs/6-decode.md says how each rule of
docs/specs/4-media-types.md (R1, R5-R10) is implemented; the timestamp math is pure and lives
in the module-level functions below."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import av
import numpy as np
from av.error import FFmpegError  # every PyAV error subclasses it
from av.video.frame import VideoFrame
from av.video.reformatter import Interpolation
from numpy.typing import NDArray

from tapesift.media.safe_open import open_media
from tapesift.media.types import (
    AUDIO_GAP_FILL_S,
    EARLY_EOF_S,
    MAX_GAP_WARNINGS,
    MAX_SIDE_PX,
    AssetInfo,
    AudioChunk,
    DecodeError,
    Frame,
)
from tapesift.warning_codes import AssetWarning, WarningCode, WarningSink

if TYPE_CHECKING:
    from av.audio.frame import AudioFrame
    from av.audio.stream import AudioStream
    from av.codec.context import CodecContext
    from av.container import InputContainer
    from av.rational import AVRational
    from av.stream import Stream
    from av.video.stream import VideoStream

log = logging.getLogger(__name__)

Kind = Literal["video", "audio"]
Run = tuple[float, float | None]


# ---- pure timestamp math (no I/O, no PyAV objects) ----


def half_up(x: float) -> int:
    """math.floor(x + 0.5). The only rounding used in this module; round() is never used."""
    return math.floor(x + 0.5)


def clock_s(pts: int, time_base: Fraction, container_start_s: float) -> float:
    """R1 step 1: float(pts * time_base) - container_start_s."""
    return float(pts * time_base) - container_start_s


def frame_kept(t_s: float, duration_s: float | None, last_t_s: float | None) -> bool:
    """R1 steps 2-3 and R7 step 2: t_s >= 0, t_s < duration_s when known, t_s > last_t_s when
    known."""
    return (
        t_s >= 0
        and (duration_s is None or t_s < duration_s)
        and (last_t_s is None or t_s > last_t_s)
    )


def window_index(t_s: float, every_s: float) -> int:
    """R7 step 3: floor(t_s / every_s + 1e-9)."""
    return math.floor(t_s / every_s + 1e-9)


def upright_size(h: int, w: int) -> tuple[int, int]:
    """R6 on an upright (h, w): unchanged when max(h, w) <= MAX_SIDE_PX; else each side becomes
    max(1, half_up(side * MAX_SIDE_PX / max(h, w)))."""
    m = max(h, w)
    if m <= MAX_SIDE_PX:
        return h, w
    # int * int / int: one correctly rounded division, so the long side is exactly MAX_SIDE_PX.
    return max(1, half_up(h * MAX_SIDE_PX / m)), max(1, half_up(w * MAX_SIDE_PX / m))


@dataclass(frozen=True, slots=True)
class Placement:
    new_run: bool  # start a new run at start_s (flushes the pending chunk)
    start_s: float  # container-clock time of the first kept sample
    fill: int  # zeros written before the kept samples; always 0 when new_run
    skip: int  # leading samples dropped (overlap with the run, or t < 0)
    keep: int  # samples kept after skip; samples at or past duration_s are cut


def place_audio(
    t_s: float | None,
    n: int,
    *,
    sample_rate: int,
    run_end_s: float | None,
    duration_s: float | None,
) -> Placement:
    """R1 steps 2-3 and R8 for one resampled frame of n samples whose first sample is at t_s."""
    if t_s is None:
        if run_end_s is None:
            return Placement(False, 0.0, 0, 0, 0)  # neutral: nothing to continue
        t_s = run_end_s  # no PTS: continue the run
    fill = skip = 0
    if run_end_s is None or t_s - run_end_s > AUDIO_GAP_FILL_S:
        new_run = True
        first = t_s
    else:
        new_run = False
        gap = t_s - run_end_s
        if gap > 1 / sample_rate:
            fill = half_up(gap * sample_rate)
        elif gap < 0:
            skip = min(n, half_up(-gap * sample_rate))
        first = run_end_s + fill / sample_rate  # on the run's sample clock
    if first < 0:  # R1 step 2
        skip = min(n, skip + math.ceil(-first * sample_rate - 1e-9))
        first = t_s + skip / sample_rate
    keep = n - skip
    if duration_s is not None:  # R1 step 3
        keep = min(keep, max(0, math.ceil((duration_s - first) * sample_rate - 1e-9)))
    if keep == 0:
        fill = 0
    return Placement(new_run, first, fill, skip, keep)


def chunk_runs(
    pieces: Iterable[tuple[bool, float, NDArray[np.float32]]],
    *,
    chunk_n: int,
    sample_rate: int,
) -> Iterator[AudioChunk]:
    """R8 chunking of (new_run, start_s, samples) pieces, zero fill already prepended.
    An empty new_run piece still starts a new run at its start_s; an empty continuing piece is
    a no-op. Never yields an empty chunk."""
    buf = np.empty(chunk_n, np.float32)
    filled = 0  # samples in buf
    in_run = False
    run_start = 0.0
    run_done = 0  # samples of the current run already yielded

    def chunk(n: int) -> AudioChunk:
        out = buf[:n] if n < chunk_n else buf
        np.clip(out, -1.0, 1.0, out=out)  # AAC can overshoot; M0 documents [-1, 1]
        return AudioChunk(run_start + run_done / sample_rate, out, sample_rate)

    for new_run, start_s, samples in pieces:
        if new_run or not in_run:
            in_run = True
            if filled:
                yield chunk(filled)
                buf = np.empty(chunk_n, np.float32)
            run_start, run_done, filled = start_s, 0, 0
        pos = 0
        while pos < samples.size:
            take = min(chunk_n - filled, samples.size - pos)
            buf[filled : filled + take] = samples[pos : pos + take]
            filled += take
            pos += take
            if filled == chunk_n:
                yield chunk(chunk_n)
                buf = np.empty(chunk_n, np.float32)  # a fresh buffer: chunks own their arrays
                run_done += chunk_n
                filled = 0
    if filled:
        yield chunk(filled)


@dataclass(frozen=True, slots=True)
class GapState:
    last_good_end_s: float = 0.0  # `a` for the next run (R10)
    open_from_s: float | None = None  # `a` of the open run; None when no run is open


def gap_on_good(
    state: GapState, start_s: float, end_s: float
) -> tuple[GapState, tuple[float, float] | None]:
    """A good item. Closes an open run at start_s and returns that run's raw (a, b)."""
    run = None if state.open_from_s is None else (state.open_from_s, start_s)
    return GapState(end_s, None), run


def gap_on_fail(state: GapState) -> GapState:
    """A failed item. Opens a run at last_good_end_s if none is open; otherwise a no-op."""
    if state.open_from_s is not None:
        return state
    return GapState(state.last_good_end_s, state.last_good_end_s)


def gap_on_flush(state: GapState, end_s: float) -> GapState:
    """A good item from the end-of-stream flush (owner ruling, amends R10). It never closes an
    open run: an open run's start moves to end_s and stays open to EOF. With no open run it
    acts like gap_on_good: last_good_end_s becomes end_s."""
    return GapState(end_s, None if state.open_from_s is None else end_s)


def gap_on_eof(state: GapState, duration_s: float | None) -> Run | None:
    """R10 at EOF (amended). If a run is open, close it at duration_s (None as b means "end").
    If no run is open, i.e. the stream's last decode step was clean, and duration_s is not None
    and state.last_good_end_s < duration_s - EARLY_EOF_S, return the early-EOF run
    (last_good_end_s, duration_s). Earlier closed runs don't matter. Otherwise None."""
    if state.open_from_s is not None:
        return state.open_from_s, duration_s
    if duration_s is not None and state.last_good_end_s < duration_s - EARLY_EOF_S:
        return state.last_good_end_s, duration_s
    return None


def clamp_run(run: Run, duration_s: float | None) -> Run | None:
    """Ruling: a = max(a, 0.0); b = min(b, duration_s) when both are known. None when b <= a,
    so the run emits nothing and does not count toward the cap."""
    a, b = max(run[0], 0.0), run[1]
    if b is not None and duration_s is not None:
        b = min(b, duration_s)
    if b is not None and b <= a:
        return None
    return a, b


def gap_warning(kind: Kind, index: int, run: Run, sent: int) -> AssetWarning | None:
    """PARTIAL_DECODE "<kind> stream <index>: undecodable <a:.2f>-<b:.2f> s" for a clamped run
    (b may be "end"). None once `sent` reaches MAX_GAP_WARNINGS."""
    if sent >= MAX_GAP_WARNINGS:
        return None
    a, b = run
    end = "end" if b is None else f"{b:.2f}"
    return AssetWarning(
        WarningCode.PARTIAL_DECODE, f"{kind} stream {index}: undecodable {a:.2f}-{end} s"
    )


def gap_summary(total_runs: int) -> AssetWarning | None:
    """PARTIAL_DECODE "<total_runs - MAX_GAP_WARNINGS> more undecodable runs not listed", or None
    when total_runs <= MAX_GAP_WARNINGS."""
    if total_runs <= MAX_GAP_WARNINGS:
        return None
    return AssetWarning(
        WarningCode.PARTIAL_DECODE,
        f"{total_runs - MAX_GAP_WARNINGS} more undecodable runs not listed",
    )


# ---- the decoder ----


def _fraction(tb: AVRational) -> Fraction:
    return Fraction(tb.numerator, tb.denominator)


class _Gaps:
    """R10 bookkeeping for one iter_* call: the gap state, the warning cap and the summary."""

    def __init__(self, warn: WarningSink, kind: Kind, index: int, duration_s: float | None) -> None:
        self.warn: WarningSink = warn
        self.kind: Kind = kind
        self.index = index
        self.duration_s = duration_s
        self.state = GapState()
        self.total = 0  # runs that survived clamp_run

    def fail(self) -> None:
        self.state = gap_on_fail(self.state)

    def good(self, start_s: float, end_s: float, *, flush: bool) -> None:
        if flush:
            self.state = gap_on_flush(self.state, end_s)
            return
        self.state, run = gap_on_good(self.state, start_s, end_s)
        if run is not None:
            self._report(run)

    def eof(self) -> None:
        """Only on normal exhaustion, never in `finally`: an early close skips it."""
        run = gap_on_eof(self.state, self.duration_s)
        if run is not None:
            self._report(run)
        summary = gap_summary(self.total)
        if summary is not None:
            self.warn(summary)

    def _report(self, run: Run) -> None:
        clamped = clamp_run(run, self.duration_s)
        if clamped is None:
            return
        warning = gap_warning(self.kind, self.index, clamped, min(self.total, MAX_GAP_WARNINGS))
        self.total += 1
        if warning is not None:
            self.warn(warning)  # never wrapped: a raising sink propagates


def _open(asset: AssetInfo) -> InputContainer:
    try:
        return open_media(Path(asset.path))  # checked fd, allowed formats, one timeout (#21)
    except (FFmpegError, OSError) as e:
        raise DecodeError(WarningCode.UNREADABLE, f"cannot open: {e}") from e


def _stream(container: InputContainer, index: int, kind: Kind, codec: str) -> Stream:
    """The stream probe selected (R4: never re-selected), checked as in spec steps 5-6."""
    streams = container.streams
    if not 0 <= index < len(streams) or streams[index].type != kind:
        raise DecodeError(WarningCode.UNREADABLE, f"{kind} stream {index}: not in container")
    stream = streams[index]
    if cast("CodecContext | None", stream.codec_context) is None:
        raise DecodeError(
            WarningCode.UNSUPPORTED_CODEC,
            f"{kind} stream {index}: no decoder for codec '{codec}'",
        )
    return stream


def _packets(
    container: InputContainer,
    stream: VideoStream | AudioStream,
    gaps: _Gaps,
    extra: dict[str, str],
) -> Iterator[tuple[bool, Sequence[object]]]:
    """(is_flush, decoded frames) per packet. Decode failures are gap failures; a demux error
    is one too, and stops demuxing with the run left open to EOF (the decoder isn't drained)."""
    packets = container.demux(stream)
    while True:
        try:
            packet = next(packets)
        except StopIteration:
            return
        except FFmpegError as e:
            log.debug("demux failed: %s", e, extra=extra)
            gaps.fail()
            return
        flush = packet.size == 0  # the empty packet demux sends to drain the decoder
        try:
            frames = packet.decode()
        except FFmpegError as e:
            log.debug("decode failed (flush=%s): %s", flush, e, extra=extra)
            if not flush:  # the end-of-stream flush is never a failure
                gaps.fail()
            continue
        yield flush, frames


def _upright(frame: VideoFrame, quarter_turns: int) -> NDArray[np.uint8]:
    """R5 then R6, literally: rgb24 at stored size, rot90, AREA resize, C-contiguous."""
    arr = np.rot90(cast("NDArray[np.uint8]", frame.to_ndarray(format="rgb24")), quarter_turns)
    h2, w2 = upright_size(arr.shape[0], arr.shape[1])
    if (h2, w2) != arr.shape[:2]:
        small = VideoFrame.from_ndarray(np.ascontiguousarray(arr), format="rgb24").reformat(
            width=w2, height=h2, interpolation=Interpolation.AREA
        )
        arr = cast("NDArray[np.uint8]", small.to_ndarray())
    return np.ascontiguousarray(arr)  # Frame copies it if it doesn't own its memory


class PyAVDecoder:
    """M0's Decoder on the CPU via PyAV. Stateless; one instance serves any number of assets."""

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        if every_s is not None and not (math.isfinite(every_s) and every_s > 0):
            raise ValueError(f"every_s must be > 0, got {every_s}")
        video = asset.video
        if video is None:
            return  # ruling 4: nothing to decode, the file is never opened
        extra = {"asset_id": asset.id, "stage": "decode"}
        with _open(asset) as container:
            stream = cast("VideoStream", _stream(container, video.index, "video", video.codec))
            start_s = (container.start_time or 0) / 1e6
            gaps = _Gaps(warn, "video", video.index, asset.duration_s)
            last_t: float | None = None
            last_k = -1
            for flush, frames in _packets(container, stream, gaps, extra):
                for frame in cast("list[VideoFrame]", frames):
                    if frame.pts is None:
                        continue  # neutral
                    t = clock_s(frame.pts, _fraction(frame.time_base), start_s)
                    k = -1 if every_s is None else window_index(t, every_s)
                    pixels = None
                    if frame_kept(t, asset.duration_s, last_t) and (every_s is None or k > last_k):
                        try:
                            pixels = _upright(frame, video.rotation // 90)
                        except FFmpegError as e:
                            log.debug("convert failed at %.3f s: %s", t, e, extra=extra)
                            gaps.fail()  # failed only, never also good
                            continue
                    gaps.good(t, t, flush=flush)
                    if pixels is not None:
                        last_t, last_k = t, k
                        yield Frame(t, pixels)
            gaps.eof()

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        if not (math.isfinite(sample_rate) and sample_rate > 0):
            raise ValueError(f"sample_rate must be > 0, got {sample_rate}")
        if not (math.isfinite(chunk_s) and chunk_s > 0):
            raise ValueError(f"chunk_s must be > 0, got {chunk_s}")
        chunk_n = half_up(chunk_s * sample_rate)
        if chunk_n < 1:
            raise ValueError(f"chunk_s * sample_rate rounds to {chunk_n} samples; need >= 1")
        if track is not None and not 0 <= track < len(asset.audio):
            raise ValueError(f"track {track} not in 0..{len(asset.audio) - 1}")
        info = asset.default_audio if track is None else asset.audio[track]
        if info is None:
            return  # ruling 4: nothing to decode, the file is never opened
        extra = {"asset_id": asset.id, "stage": "decode"}
        with _open(asset) as container:
            stream = cast("AudioStream", _stream(container, info.index, "audio", info.codec))
            gaps = _Gaps(warn, "audio", info.index, asset.duration_s)
            pieces = _audio_pieces(container, stream, asset, sample_rate, gaps, extra)
            yield from chunk_runs(pieces, chunk_n=chunk_n, sample_rate=sample_rate)
            gaps.eof()


def _audio_pieces(
    container: InputContainer,
    stream: AudioStream,
    asset: AssetInfo,
    sample_rate: int,
    gaps: _Gaps,
    extra: dict[str, str],
) -> Iterator[tuple[bool, float, NDArray[np.float32]]]:
    """Decoded audio -> mono float32 at sample_rate (FFmpeg downmixes) -> chunk_runs pieces."""
    start_s = (container.start_time or 0) / 1e6
    resampler = av.AudioResampler(format="flt", layout="mono", rate=sample_rate)
    in_run = False
    run_start = 0.0
    run_n = 0  # samples placed in the current run: an integer clock, so run_end never drifts

    def place(rf: AudioFrame) -> tuple[bool, float, NDArray[np.float32]] | None:
        nonlocal in_run, run_start, run_n
        t = None if rf.pts is None else clock_s(rf.pts, _fraction(rf.time_base), start_s)
        p = place_audio(
            t,
            rf.samples,
            sample_rate=sample_rate,
            run_end_s=run_start + run_n / sample_rate if in_run else None,
            duration_s=asset.duration_s,
        )
        if p.new_run:
            in_run, run_start, run_n = True, p.start_s, 0
        elif p.keep == 0:
            return None  # an empty continuing piece is a no-op
        mono = cast("NDArray[np.float32]", rf.to_ndarray()).reshape(-1)
        body = mono[p.skip : p.skip + p.keep]
        data = np.concatenate([np.zeros(p.fill, np.float32), body]) if p.fill else body
        run_n += data.size
        return p.new_run, p.start_s, data

    for flush, frames in _packets(container, stream, gaps, extra):
        for frame in cast("list[AudioFrame]", frames):
            try:
                out = resampler.resample(frame)
            except (FFmpegError, ValueError) as e:  # ValueError: format/layout/rate changed
                log.debug("resample failed: %s", e, extra=extra)
                gaps.fail()  # failed only, never also good
                continue
            if frame.pts is not None:
                t = clock_s(frame.pts, _fraction(frame.time_base), start_s)
                gaps.good(t, t + frame.samples / frame.sample_rate, flush=flush)
            for rf in out:
                if (piece := place(rf)) is not None:
                    yield piece
    try:
        tail = resampler.resample(None)
    except FFmpegError as e:
        log.debug("resampler flush failed: %s", e, extra=extra)
        tail = []
    for rf in tail:
        if (piece := place(rf)) is not None:
            yield piece
