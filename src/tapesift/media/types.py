"""Types and rules shared by probe (E1), decode backends (E2, later NVDEC) and their callers.
The rules are written out in docs/specs/4-media-types.md, "Rules"."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from tapesift.warning_codes import AssetWarning, StageError, WarningCode, WarningSink

# ponytail: module constants until config.py exists; then they become config defaults.
MAX_SIDE_PX = 768  # upright frames are downscaled so max(h, w) <= this
SHORT_CLIP_S = 1.0  # SHORT_CLIP when duration_s < this
AUDIO_GAP_FILL_S = 0.5  # audio PTS gaps up to this are zero-filled; longer gaps split chunks
MAX_GAP_WARNINGS = 20  # PARTIAL_DECODE warnings per iter_* call before one summary warning
EARLY_EOF_S = 1.0  # a clean EOF more than this before duration_s counts as a gap run (R10)


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """The output schema's asset.video block, plus `index`."""

    index: int  # container stream index; decoders decode exactly this stream
    codec: str  # FFmpeg codec name, e.g. "h264"; "unknown" when FFmpeg has no codec for it
    w: int | None  # STORED width, before rotation; None when the container does not say
    h: int | None  # STORED height, before rotation; None when the container does not say
    fps_avg: float | None  # average frame rate; None when unknown or zero
    vfr: bool  # False when it cannot be determined
    rotation: int  # 0, 90, 180 or 270: counterclockwise degrees to display upright, equal to
    # ffprobe's display-matrix `rotation` mod 360; 0 when absent. Displayed size is (h, w)
    # swapped when rotation is 90 or 270.


@dataclass(frozen=True, slots=True)
class AudioStreamInfo:
    """One audio stream. The schema's asset.audio block is derived from these: codec and lang
    of AssetInfo.default_audio, tracks = len(AssetInfo.audio)."""

    index: int  # container stream index
    codec: str  # FFmpeg codec name, or "unknown"
    lang: str | None  # container language tag as written, e.g. "eng"; None if absent
    default: bool  # the container's default disposition


@dataclass(frozen=True, slots=True)
class AssetInfo:
    """What probe learns from container metadata."""

    id: str  # ADR 0012 (refines D6). Default: "tsid1:" + 64 lowercase hex of
    # sha256(8-byte big-endian size || first 8 MiB || last 8 MiB, no overlap); "tsid1"
    # versions the whole scheme, chunk size included. full_hash=True: "sha256:" + 64 lowercase
    # hex of the plain file sha256. Shape: ^(tsid1|sha256):[0-9a-f]{64}$
    path: Path  # as given to probe; may contain any Unicode and spaces
    duration_s: float | None  # the duration rule; None when nothing reports a duration
    video: VideoInfo | None  # None for audio-only files, including audio with cover art
    audio: tuple[AudioStreamInfo, ...]  # container stream order; empty means NO_AUDIO
    warnings: tuple[AssetWarning, ...]  # normalized on construction: deduplicated by
    # (code, detail) and sorted by (code, detail). Informational; decoders never read it.
    # A non-WarningCode code is a TypeError, raised by AssetWarning before it gets here.

    def __post_init__(self) -> None:
        unique = sorted(set(self.warnings), key=lambda w: (w.code.value, w.detail))
        object.__setattr__(self, "warnings", tuple(unique))

    @property
    def default_audio(self) -> AudioStreamInfo | None:
        """First stream with default=True, else the first stream, else None."""
        return next((a for a in self.audio if a.default), self.audio[0] if self.audio else None)


@dataclass(frozen=True, slots=True, eq=False)  # eq=False: ndarray == is elementwise
class Frame:
    t_s: float  # container clock, from this frame's PTS
    pixels: NDArray[np.uint8]  # shape (h, w, 3), RGB, upright, max(h, w) <= MAX_SIDE_PX,
    # C-contiguous: decoders call np.ascontiguousarray after rot90/resize (rot90 returns a view)

    def __post_init__(self) -> None:
        if not self.pixels.flags.c_contiguous:
            raise ValueError("Frame.pixels must be C-contiguous; use np.ascontiguousarray")
        self.pixels.flags.writeable = False  # frozen does not protect array contents


@dataclass(frozen=True, slots=True, eq=False)
class AudioChunk:
    start_s: float  # container clock of samples[0], from PTS
    samples: NDArray[np.float32]  # shape (n,), n >= 1, mono, in [-1.0, 1.0];
    # samples[i] is at start_s + i / sample_rate
    sample_rate: int


class ProbeError(StageError):
    """Probe cannot produce an AssetInfo (UNREADABLE)."""

    allowed = frozenset({WarningCode.UNREADABLE})


class DecodeError(StageError):
    """A decoder cannot produce any output for this asset (UNREADABLE or UNSUPPORTED_CODEC)."""

    allowed = frozenset({WarningCode.UNREADABLE, WarningCode.UNSUPPORTED_CODEC})


class Decoder(Protocol):
    """A decode backend (PyAV now, torchcodec/NVDEC later). It must follow every rule in
    docs/specs/4-media-types.md, "Rules"."""

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]: ...

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]: ...
