"""E1: read container metadata into AssetInfo, with the probe-owned warning codes.
Rules R2-R5 and R11 are in docs/specs/4-media-types.md; exact details in docs/specs/5-probe.md.
Probe opens codec headers when color_trc is unspecified but decodes no frames, and runs no
external programs. Files open as "file:" URLs with only the file protocol allowed, so a
name like "concat:a|b" or a playlist inside a file cannot reach other files or the network."""

from __future__ import annotations

import dataclasses
import logging
import math
import struct
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

import av
import av.error
from av.stream import Disposition

from tapesift.media.asset_id import asset_id
from tapesift.media.types import (
    MAX_SIDE_PX,
    SHORT_CLIP_S,
    AssetInfo,
    AudioStreamInfo,
    ProbeError,
    VideoInfo,
)
from tapesift.warning_codes import AssetWarning, WarningCode

if TYPE_CHECKING:
    from av.packet import PktSideDataT

log = logging.getLogger(__name__)

type _Add = Callable[[WarningCode, str], None]

PROBE_TIMEOUT_S: Final = 30.0  # card 2; module constant until config.py exists
NVDEC_CODECS: Final = frozenset(
    {"h264", "hevc", "av1", "vp8", "vp9", "mpeg1video", "mpeg2video", "mpeg4", "vc1", "mjpeg"}
)  # card 3

_TRC_UNSPECIFIED: Final = 2  # AVCOL_TRC_UNSPECIFIED
_HDR_TRC: Final = {16: "PQ", 18: "HLG"}  # SMPTE2084, ARIB_STD_B67 (R11)
_FIELD_ORDER: Final = {2: "tt", 3: "bb", 4: "tb", 5: "bt"}  # R11
_VFR_RATIO: Final = 0.01  # T1
_START_OFFSET_S: Final = 0.25  # T1
_AV_MISMATCH_S: Final = 1.0  # T1


class _Rational(Protocol):  # av.AVRational; fractions.Fraction in stand-ins
    @property
    def numerator(self) -> int: ...
    @property
    def denominator(self) -> int: ...
    def __bool__(self) -> bool: ...
    def __float__(self) -> float: ...


class _CodecLike(Protocol):
    @property
    def name(self) -> str: ...


class _VideoCodecLike(_CodecLike, Protocol):
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def field_order(self) -> int: ...
    @property
    def color_trc(self) -> int: ...
    @property
    def coded_side_data(self) -> Mapping[PktSideDataT, bytes]: ...
    def open(self, strict: bool = True) -> None: ...  # parses headers; decodes no frames


class _StreamLike(Protocol):
    @property
    def index(self) -> int: ...
    @property
    def start_time(self) -> int | None: ...
    @property
    def duration(self) -> int | None: ...
    @property
    def time_base(self) -> _Rational: ...
    @property
    def disposition(self) -> Disposition: ...
    @property
    def average_rate(self) -> _Rational: ...
    @property
    def base_rate(self) -> _Rational: ...
    @property
    def language(self) -> str | None: ...
    @property
    def codec_context(self) -> _CodecLike | None: ...  # None when FFmpeg has no decoder


class _VideoStreamLike(_StreamLike, Protocol):
    @property
    def codec_context(self) -> _VideoCodecLike | None: ...


def _us_to_s(us: int | None) -> float | None:
    return None if us is None else us / 1e6


def _time_base(stream: _StreamLike) -> Fraction | None:
    tb = stream.time_base
    return Fraction(tb.numerator, tb.denominator) if tb else None


def _stream_start_s(stream: _StreamLike, container_start_s: float) -> float | None:
    tb = _time_base(stream)
    if stream.start_time is None or tb is None:
        return None
    return float(stream.start_time * tb) - container_start_s


def _stream_end_s(stream: _StreamLike, container_start_s: float) -> float | None:
    """R2: exact Fraction arithmetic, float last, so 1.0 s files don't land at 0.999..."""
    tb = _time_base(stream)
    if stream.start_time is None or stream.duration is None or tb is None:
        return None
    return float((stream.start_time + stream.duration) * tb) - container_start_s


def _rotation_from_matrix(matrix: bytes | None) -> int:
    """R5: FFmpeg's av_display_rotation_get, normalized to [0, 360), rounded half up to 90."""
    if matrix is None or len(matrix) != 36:
        return 0
    m = struct.unpack("=9i", matrix)
    s0, s1 = math.hypot(m[0], m[3]), math.hypot(m[1], m[4])
    if s0 == 0 or s1 == 0:
        return 0
    deg = round(-math.degrees(math.atan2(m[1] / s1, m[0] / s0)), 6) % 360
    return (math.floor(deg / 90 + 0.5) * 90) % 360


def _select_video(videos: Sequence[_VideoStreamLike]) -> _VideoStreamLike | None:
    """R4: the first video stream that is not cover art."""
    return next((v for v in videos if not v.disposition & Disposition.attached_pic), None)


def _color_trc(cc: _VideoCodecLike) -> int:
    """Some containers (hdr10.mkv) carry the transfer only in the codec headers, which PyAV 19
    reads when the decoder opens. A failed open means "unknown" (owner's card, 2026-10-17)."""
    if cc.color_trc != _TRC_UNSPECIFIED:
        return cc.color_trc
    try:
        cc.open(strict=False)
    except av.error.FFmpegError:
        return _TRC_UNSPECIFIED
    return cc.color_trc


def probe(path: Path, *, full_hash: bool = False) -> AssetInfo:
    """Raises ProbeError(UNREADABLE, reason) when the file cannot be opened as media or has no
    audio or video stream. Never raises a PyAV exception."""
    try:
        with av.open(
            "file:" + str(path.resolve()),
            options={"protocol_whitelist": "file"},
            timeout=PROBE_TIMEOUT_S,
        ) as container:
            info = _read(
                AssetInfo(asset_id(path, full=full_hash), path, None, None, (), ()),
                _select_video(container.streams.video),
                container.streams.audio,
                _us_to_s(container.start_time) or 0.0,
                _us_to_s(container.duration),
            )
    except (av.error.FFmpegError, OSError) as e:
        raise ProbeError(WarningCode.UNREADABLE, f"{type(e).__name__}: {e.strerror or e}") from e
    log.debug("probed", extra={"asset_id": info.id, "stage": "probe"})
    return info


def _read(
    info: AssetInfo,
    vs: _VideoStreamLike | None,
    audio_streams: Sequence[_StreamLike],
    c_start: float,
    c_duration: float | None,
) -> AssetInfo:
    if vs is None and not audio_streams:
        raise ProbeError(WarningCode.UNREADABLE, "no audio or video stream")
    warnings: list[AssetWarning] = []

    def add(code: WarningCode, detail: str) -> None:
        warnings.append(AssetWarning(code, detail))

    audio = tuple(
        AudioStreamInfo(
            index=s.index,
            codec=s.codec_context.name if s.codec_context else "unknown",
            lang=s.language,
            default=bool(s.disposition & Disposition.default),
        )
        for s in audio_streams
    )
    for s in audio_streams:
        if s.codec_context is None:
            add(WarningCode.UNSUPPORTED_CODEC, f"stream {s.index} codec unknown: no decoder")
    info = dataclasses.replace(info, audio=audio)
    da = info.default_audio
    da_stream = next((s for s in audio_streams if da and s.index == da.index), None)
    a_end = _stream_end_s(da_stream, c_start) if da_stream else None

    video: VideoInfo | None = None
    v_end: float | None = None
    if vs is not None:
        video, v_end = _video(vs, c_start, add)
        if video.rotation:
            add(
                WarningCode.ROTATED,
                f"video stream {vs.index}: display matrix rotation {video.rotation} deg",
            )
        if not audio:
            add(WarningCode.NO_AUDIO, "no audio stream; ASR skipped")
        # ponytail: AV_LENGTH_MISMATCH needs both stream ends, so MKV/WebM (no per-stream
        # duration) are never flagged; upgrade path is scanning the last packets' PTS.
        if (
            v_end is not None
            and a_end is not None
            and da_stream is not None
            and abs(v_end - a_end) > _AV_MISMATCH_S
        ):
            add(
                WarningCode.AV_LENGTH_MISMATCH,
                f"video stream {vs.index} ends at {v_end:.2f} s, "
                f"audio stream {da_stream.index} ends at {a_end:.2f} s",
            )

    starts = [("video", vs), ("audio", da_stream)]
    parts = [
        f"{kind} stream {s.index} starts at {t:.2f} s"
        for kind, s in starts
        if s is not None
        and (t := _stream_start_s(s, c_start)) is not None
        and abs(t) > _START_OFFSET_S
    ]
    if parts:
        add(WarningCode.START_OFFSET, "; ".join(parts))
    if len(audio) >= 2 and da is not None:
        add(WarningCode.MULTI_AUDIO, f"{len(audio)} audio streams; default is stream {da.index}")

    end = v_end if vs is not None else a_end  # R3
    duration_s = end if end is not None else c_duration
    if duration_s is not None and duration_s < SHORT_CLIP_S:
        add(WarningCode.SHORT_CLIP, f"duration {duration_s:.2f} s")
    return dataclasses.replace(info, duration_s=duration_s, video=video, warnings=tuple(warnings))


def _video(vs: _VideoStreamLike, c_start: float, add: _Add) -> tuple[VideoInfo, float | None]:
    v = vs.index
    cc = vs.codec_context
    avg, base = vs.average_rate, vs.base_rate
    # ponytail: VFR from metadata only; phone video within 1% of nominal is missed (times stay
    # right, E2 uses PTS). Upgrade path: scan PTS gaps over the first N packets.
    vfr = bool(avg and base and abs(float(avg) - float(base)) / float(base) > _VFR_RATIO)
    if vfr:
        add(
            WarningCode.VFR_DETECTED,
            f"video stream {v}: average {float(avg):.2f} fps vs "
            f"nominal {float(base):.2f} fps; times from PTS",
        )
    if cc is None:
        add(WarningCode.UNSUPPORTED_CODEC, f"stream {v} codec unknown: no decoder")
        info = VideoInfo(v, "unknown", None, None, float(avg) if avg else None, vfr, 0)
        return info, _stream_end_s(vs, c_start)
    if cc.name not in NVDEC_CODECS:
        add(WarningCode.UNSUPPORTED_CODEC, f"stream {v} codec {cc.name}: no NVDEC, CPU decode")
    w, h = cc.width or None, cc.height or None
    rotation = _rotation_from_matrix(cc.coded_side_data.get("display_matrix"))
    if cc.field_order in _FIELD_ORDER:
        add(
            WarningCode.INTERLACED,
            f"video stream {v}: field order {_FIELD_ORDER[cc.field_order]}; not deinterlaced",
        )
    if w is not None and h is not None and max(w, h) > MAX_SIDE_PX:
        add(
            WarningCode.DOWNSCALED,
            f"video stream {v}: {w}x{h} downscaled to {MAX_SIDE_PX} px long side",
        )
    trc = _color_trc(cc)  # last: opening the decoder must not change what was read above
    if trc in _HDR_TRC:
        add(
            WarningCode.HDR_CONVERTED,
            f"video stream {v}: {_HDR_TRC[trc]} transfer; decoded to 8-bit, not tone-mapped",
        )
    info = VideoInfo(v, cc.name, w, h, float(avg) if avg else None, vfr, rotation)
    return info, _stream_end_s(vs, c_start)
