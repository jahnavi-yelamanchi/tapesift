# 4. Media types, warning codes and the Decoder protocol

Issue: #4   Lane: Media   Status: approved 2026-10-16 (owner, gate 1; T3 cards decided after council, T2 cards accepted as recommended)

## Goal
E1 (#5, probe) and E2 (#6, CPU decode) can build in parallel against one source of truth. This PR puts on main:
- the shared types: `AssetInfo`, stream info, `Frame`, `AudioChunk`, `WarningCode`, `AssetWarning`, the stage errors and the `Decoder` Protocol;
- the stream-selection, clock, sampling, duration and detection rules;
- the base dependencies, numpy and PyAV;
- the `UNREADABLE` code and two new fixtures.

## Read first
- docs/spec.md: Architecture (Interfaces), CLI, config and output schema (`asset` and `warnings` blocks), Messy multimodal data, Engineering standards (Code structure rules)
- ADRs: 0006 (fixtures), 0008 (fakes locally), 0010 (English only), 0011 (Python 3.12 floor, being written)
- Code: `src/tapesift/cli/doctor.py` (house style), `tests/unit/test_fixtures.py` (`spec_warning_codes()`), `scripts/make_fixtures.py` (the `Fixture` table and `main`), `tests/fixtures/manifest.json`

This spec is the source of truth for E1 and E2, whose specs are rewritten against it. Where it disagrees with docs/spec.md on the Decoder, this spec wins, and this PR updates docs/spec.md.

## Scope
May change:
- `src/tapesift/warning_codes.py` (new)
- `src/tapesift/media/__init__.py` (new, docstring only)
- `src/tapesift/media/types.py` (new)
- `tests/unit/test_media_types.py` (new)
- `tests/unit/test_fixtures.py`: add one test. In the `spec_warning_codes` docstring, replace the sentence starting "When E1 adds the WarningCode enum" with "test_warning_code_enum_matches_spec checks the WarningCode enum against this set." Nothing is removed or loosened.
- `pyproject.toml`, `uv.lock`: add `av` and `numpy` only. M0 is the only PR that adds them; E1 and E2 never touch these files.
- `docs/spec.md`, two places only:
  - the `class Decoder` lines in Architecture, Interfaces;
  - one new `UNREADABLE` row in the messy-data table (exact text below).
- `scripts/make_fixtures.py`: two fixtures and a `media` flag (exact change below)
- `tests/fixtures/not_media.txt`, `tests/fixtures/rotated_270.mp4` (new), `tests/fixtures/manifest.json`
- `THIRD_PARTY.md`: rows for av and numpy
- `CHANGELOG.md`: one line under Unreleased, Added: "- Shared media types, the `UNREADABLE` warning code and the `Decoder` protocol; numpy and PyAV become dependencies." Each PR adds its own line, and conflicts are resolved at rebase by keeping all lines.

Must not touch:
- `src/tapesift/media/probe.py`, `src/tapesift/media/asset_id.py` (E1), `src/tapesift/media/decode.py` (E2)
- `requires-python`, the ruff/pyright targets, CI, and the "Python 3.11+" line in docs/spec.md. The ADR 0011 PR owns all of these.
- Existing fixture files (they must stay byte-identical), `src/tapesift/cli/`, and everything else

## Interfaces touched
Before: nothing. The only definition is the illustrative block in docs/spec.md.

After: the files below, exactly. Docstrings and comments are part of the contract.

### `src/tapesift/warning_codes.py`
```python
"""Warning codes from the messy-data table in docs/spec.md, and the error every stage raises.
Imports nothing outside the stdlib."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class WarningCode(StrEnum):
    """Exactly the codes in docs/spec.md, Messy multimodal data. A test keeps them in sync."""

    VFR_DETECTED = "VFR_DETECTED"
    ROTATED = "ROTATED"
    START_OFFSET = "START_OFFSET"
    AV_LENGTH_MISMATCH = "AV_LENGTH_MISMATCH"
    NO_AUDIO = "NO_AUDIO"
    MULTI_AUDIO = "MULTI_AUDIO"
    LOW_SPEECH = "LOW_SPEECH"
    PARTIAL_DECODE = "PARTIAL_DECODE"  # some output was produced, some was lost
    UNREADABLE = "UNREADABLE"  # not media, or cannot be opened at all
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    INTERLACED = "INTERLACED"
    CROPPED = "CROPPED"
    HDR_CONVERTED = "HDR_CONVERTED"
    SHORT_CLIP = "SHORT_CLIP"
    DOWNSCALED = "DOWNSCALED"
    DUPLICATE = "DUPLICATE"
    MEDIA_TEXT = "MEDIA_TEXT"


@dataclass(frozen=True, slots=True)
class AssetWarning:
    """One entry of the output schema's `warnings` list: {"code": ..., "detail": ...}."""

    code: WarningCode
    detail: str  # human-readable, names the cause, e.g. "video stream 0: undecodable 2.75-5.00 s"

    def __post_init__(self) -> None:
        # pyright already rejects a plain str; this catches untyped callers at runtime.
        if not isinstance(self.code, WarningCode):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"code must be a WarningCode, got {self.code!r}")


WarningSink = Callable[[AssetWarning], None]
"""Where streaming stages report non-fatal warnings. Callers usually pass `some_list.append`.
If the sink raises, the exception propagates out of the iterator; stages never catch it."""


class StageError(Exception):
    """Base for every stage's per-file failure. The runner catches this, records `.warning`
    on the asset, and moves to the next file. Picklable, so it crosses worker processes.
    Programmer errors (bad arguments) raise ValueError instead and are not caught per file."""

    def __init__(self, code: WarningCode, detail: str) -> None:
        super().__init__(code, detail)  # args=(code, detail) keeps pickle working
        self.warning = AssetWarning(code, detail)

    def __str__(self) -> str:
        return f"{self.warning.code}: {self.warning.detail}"
```

### `src/tapesift/media/types.py`
```python
"""Types and rules shared by probe (E1), decode backends (E2, later NVDEC) and their callers.
The rules are written out in docs/specs/4-media-types.md, "Rules"."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from tapesift.warning_codes import AssetWarning, StageError, WarningSink

# ponytail: module constants until config.py exists; then they become config defaults.
MAX_SIDE_PX = 768  # upright frames are downscaled so max(h, w) <= this
SHORT_CLIP_S = 1.0  # SHORT_CLIP when duration_s < this
AUDIO_GAP_FILL_S = 0.5  # audio PTS gaps up to this are zero-filled; longer gaps split chunks
MAX_GAP_WARNINGS = 20  # PARTIAL_DECODE warnings per iter_* call before one summary warning


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

    id: str  # format per decision D6 and E1's asset_id: "sha256:<64 hex>" by default,
    # "sha256-full:<64 hex>" with full_hash=True
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


class DecodeError(StageError):
    """A decoder cannot produce any output for this asset (UNREADABLE or UNSUPPORTED_CODEC)."""


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
```

### E1's entry point (E1 writes it; fixed here)
```python
# src/tapesift/media/probe.py
def probe(path: Path, *, full_hash: bool = False) -> AssetInfo:
    """Raises ProbeError(UNREADABLE, reason) when the file cannot be opened as media or has no
    audio or video stream. Never raises a PyAV exception."""
```

### Rules
Both E1 and E2 follow these rules. Each rule ends with "Tested by", naming the PR whose tests cover it: M0 (types and fakes, this PR), E1 or E2.

**R1. Clock.** Every time is seconds on the container clock, applied in this order:
1. `t = pts * stream.time_base - container_start_s`, where `container_start_s` is the container's `start_time` in seconds (0.0 if unset).
2. Drop items with `t < 0`.
3. Drop items with `t >= asset.duration_s` when it is not None. For audio, trim the final chunk at `duration_s`.

Never use frame_index / fps. Tested by: E2 (vfr.mp4 within 1 frame of PTS, start_offset.mp4 first frame near 1.5 s).

**R2. Stream ends.** A stream's end is `(stream.start_time + stream.duration) * stream.time_base - container_start_s`, and it is known only when both values are known. The container duration on the container clock is `container.duration / 1e6`. Tested by: E1.

**R3. duration_s** (E1 computes it; decoders obey it):
- With a video stream: the video stream's end, else the container duration, else None. Audio is clipped to it.
- Without one (audio-only): the default audio track's end, else the container duration, else None.
- `AV_LENGTH_MISMATCH` compares the raw stream ends from R2 (video and default audio) on the container clock, before any clipping, so it still fires on av_mismatch.mp4.

Tested by: E1 (av_mismatch.mp4, music.m4a, no_audio.mp4).

**R4. Stream selection** (E1 applies it; decoders use the result and never re-select):
- **Video:** the first stream in container order that is video and lacks the `attached_pic` disposition. An mp3 or m4a whose only video stream is cover art is audio-only: `video` is None.
- **Audio:** `AssetInfo.default_audio`.

Tested by: E1 (stream indexes on multi_audio.mkv and music.m4a); M0 (`test_default_audio_rule`).

**R5. Rotation.** Decoders take rotation only from `asset.video.rotation`, never from per-frame side data or `VideoFrame.rotation`. Upright pixels are `np.rot90(stored, rotation // 90)`. Verified with FFmpeg 7.1.1 autorotate:
- `-display_rotation 270` stores -90, so `rotation` is 270, and a red-top/blue-bottom source displays red-right.
- `rotation` 90 displays red-left.

Consumers of `w`/`h` swap them for 90 and 270. After rotating (and resizing, R6), decoders call `np.ascontiguousarray` before building the `Frame`, because `np.rot90` returns a non-contiguous view and `Frame` rejects it. Tested by: E2 (the rotated_270.mp4 pixel test); M0 (the fixture's build-time check, `test_frame_requires_contiguous_pixels`).

**R6. Downscale.** Applied after rotation:
1. If `max(h, w)` of the upright frame exceeds `MAX_SIDE_PX`, scale both sides by `s = MAX_SIDE_PX / max(h, w)`.
2. Each side becomes `max(1, floor(side * s + 0.5))` (round half up, minimum 1 px).
3. The resampling filter is E2's T1 call.

Tested by: E2 (uhd_4k.mp4 gives 768x432).

**R7. Frame sampling (`iter_frames`):**
Applied in this order to each decoded frame:
1. The R1 clock: compute `t_s`, drop `t_s < 0`, and drop `t_s >= duration_s`.
2. The monotonic drop: a frame whose `t_s` is not greater than the last yielded `t_s` is dropped, so yielded `t_s` strictly increases.
3. Windows, if `every_s` is not None:
   - The window index is `k = floor(t_s / every_s + 1e-9)`; the 1e-9 absorbs float error, so 0.3 / 0.1 lands in window 3, not 2. Windows are `[k * every_s, (k + 1) * every_s)` for k >= 0, starting at 0 on the container clock.
   - A frame is yielded when its `k` is greater than the `k` of the last yielded frame. That makes it the first frame in PTS order in its window.
   - A window with no frame yields nothing: no repeat, no warning.

`every_s=None` yields every frame that survives steps 1 and 2. `asset.video is None` yields nothing. Tested by: E2.

**R8. Audio chunks (`iter_audio`):** mono at `sample_rate`. The track is `asset.audio[track]`, or `asset.default_audio` when track is None. Within a contiguous run:
- chunks are back to back: `next.start_s == prev.start_s + len(prev.samples) / sample_rate`;
- every chunk except the run's last has exactly `round(chunk_s * sample_rate)` samples;
- no chunk is empty.

PTS discontinuities. The gap is measured on the resampled clock, at `sample_rate`. It is the next decoded audio's first-sample time (R1, from its PTS) minus the previous end, where the previous end is `prev.start_s + n_samples / sample_rate` and `n_samples` counts every sample emitted so far in the current chunk.
- A gap of at most one sample period is ignored.
- A gap of more than one sample period, up to `AUDIO_GAP_FILL_S`, is zero-filled.
- An overlap (a negative gap) drops the overlapping samples.

A run ends at the first gap greater than `AUDIO_GAP_FILL_S`, after which the next chunk starts at the new PTS, or at `duration_s`. A PTS jump alone is not a warning. `asset.audio` empty with track None yields nothing (probe already recorded NO_AUDIO). Tested by: E2 (clean.mp4 chunk sizes and contiguity, av_mismatch.mp4 trimmed at 3 s).

**R9. Argument validation.** These raise ValueError before any item is yielded (on the first `next()`, since these are generators):
- `every_s <= 0`
- `sample_rate <= 0`
- `chunk_s <= 0`
- `round(chunk_s * sample_rate) < 1`
- `track` not None and not `0 <= track < len(asset.audio)`, which includes `track=0` on an asset with no audio

Tested by: E2.

**R10. Errors and warnings.**
- `DecodeError` is raised only before the first item:
  - `UNREADABLE` when the file cannot be opened;
  - `UNSUPPORTED_CODEC` when the selected stream has no decoder in this backend.
- Decoders decide from the stream itself and never from `asset.warnings`. So probe's `UNSUPPORTED_CODEC` (for example, "no NVDEC, CPU decode" on prores.mov) never stops a CPU decode, and both entries can appear on one asset with different details.
- After the first item, bad media never raises. A **gap run** is a stretch of consecutive packets or frames of the decoded stream that fail to demux or decode. Packets without a PTS extend the current run.
  - It starts at `a`, the end time of the last good item, or 0.0 if there is none. A frame's end is its `t_s`; an audio frame's end is its last sample's time plus one sample period.
  - It ends at `b`, the `t_s` of the first good item after it, or at `duration_s` at EOF. If `duration_s` is None, `b` is the literal `end`.
  - Each gap run produces one `PARTIAL_DECODE` via `warn`, with detail `"<video|audio> stream <i>: undecodable <a>-<b> s"`, using two decimals.
  - Up to `MAX_GAP_WARNINGS` are sent per `iter_*` call.
  - Later runs are counted, and one summary `PARTIAL_DECODE` (`"<n> more undecodable runs not listed"`) is sent when the iterator is exhausted. It is skipped if the consumer closes it early.
- No backend exception type (for example, `av.FFmpegError`) escapes. Exceptions raised by `warn` propagate.
- Buffering: a decoder holds at most one chunk of audio and a fixed number of decoded frames, independent of file length. E2's acceptance tests this with a tracemalloc peak bound over a full pass of long_3h.mp4.

Tested by: E2 (truncated.mp4, unknown_codec.mov, a `warn` that raises).

**R11. Detection thresholds E1 implements** (E1 does not choose them):

| Code | Rule |
| --- | --- |
| `SHORT_CLIP` | `duration_s is not None and duration_s < SHORT_CLIP_S` |
| `HDR_CONVERTED` | video `color_trc` is SMPTE2084 (16, PQ) or ARIB_STD_B67 (18, HLG). Bit depth alone never counts: prores.mov is 10-bit SDR. |
| `INTERLACED` | video field order is tt, bb, tb or bt (PyAV `field_order` 2 to 5); progressive or unknown is not flagged |
| `DOWNSCALED` | the upright long side is greater than `MAX_SIDE_PX` |

VFR_DETECTED, START_OFFSET and AV_LENGTH_MISMATCH thresholds stay E1's T1 calls. Tested by: E1 (every probe-time code in the manifest).

### Which stage emits which code
| Code | Emitted by | How |
| --- | --- | --- |
| `VFR_DETECTED` `ROTATED` `START_OFFSET` `AV_LENGTH_MISMATCH` `NO_AUDIO` `MULTI_AUDIO` `INTERLACED` `HDR_CONVERTED` `SHORT_CLIP` `DOWNSCALED` | probe (E1) | `AssetInfo.warnings` |
| `UNREADABLE` | probe (E1); decoder (E2) if the file can't be opened at decode time | `ProbeError`; `DecodeError` |
| `UNSUPPORTED_CODEC` | probe (E1) from metadata (meaning set by E1's prores card); decoder (E2) when the stream has no decoder | `AssetInfo.warnings`; `DecodeError` (R10) |
| `PARTIAL_DECODE` | decoder (E2) only | `warn` (R10) |
| `CROPPED` | sampling (C3) | not M0, E1 or E2 |
| `LOW_SPEECH` | audio stage (E3) | not E1/E2 |
| `MEDIA_TEXT` | vision stage (E4) | not E1/E2 |
| `DUPLICATE` | runner (E7), comparing `AssetInfo.id` | not E1/E2 |

### docs/spec.md edits
In Architecture, Interfaces, the Decoder lines become:
```python
def probe(path: Path, *, full_hash: bool = False) -> AssetInfo: ...  # tapesift.media.probe; PyAV, one implementation

class Decoder(Protocol):
    def iter_frames(self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink) -> Iterator[Frame]: ...  # Frame.t_s comes from PTS
    def iter_audio(self, asset: AssetInfo, sample_rate: int = 16_000, *, track: int | None = None, chunk_s: float = 600.0, warn: WarningSink) -> Iterator[AudioChunk]: ...
```
In the messy-data table, insert this row directly after "Truncated or corrupt file":
```
| Not a media file or unopenable (e.g. `.srt`, `.DS_Store` in a folder) | One stray file aborts a folder run | probe | Skip with the exact reason | `UNREADABLE` |
```

### Fixtures (`scripts/make_fixtures.py`)
- `Fixture` gains `media: bool = True`. In `main`, `ok = fx.check(dest, probe(dest) if fx.media else {})`, because ffprobe exits non-zero on non-media.
- `not_media.txt`: `dest.write_bytes(b"not a video\n")`, codes `("UNREADABLE",)`, case "Plain text with a media-looking neighbor: not media". Its check runs ffprobe with `check=False` and the module `TIMEOUT_S`, and passes when the return code is non-zero.
- `rotated_270.mp4`: codes `("ROTATED",)`, case "Display-matrix rotation of 270 degrees; red top, blue bottom as stored". Build:
  1. Encode the stored source with `-f lavfi -i "color=c=red:size=320x240:rate=5:duration=1,drawbox=x=0:y=120:w=320:h=120:color=blue:t=fill"`, plus `X264` and `BITEXACT`.
  2. Run `-display_rotation:v:0 270 -i <src> -c copy` with `BITEXACT`.

  The check requires ffprobe side-data rotation == -90, and FFmpeg's autorotated first frame (`-frames:v 1 -f rawvideo -pix_fmt rgb24`, 240 wide x 320 high) red at (y=160, x=230) and blue at (y=160, x=10). It is about 1.8 KB.
- Regenerate with `uv run python scripts/make_fixtures.py --only not_media.txt rotated_270.mp4`. The other fixtures are not rebuilt, so their bytes and hashes do not change.
- **E2 owns the pixel test.** `iter_frames` on `rotated_270.mp4` yields a frame of shape (320, 240, 3), with `pixels[160, 230]` red (R > 200, B < 60) and `pixels[160, 10]` blue (B > 200, R < 60).
  - The frame is 320 px on its long side, so R6 does not resize it.
  - Both points are flat color at least 110 px from the red/blue boundary. FFmpeg 7.1.1 decodes them as (252, 0, 0) and (0, 0, 253).
  - So the thresholds hold for any reasonable conversion or resampling filter (nearest, bilinear, bicubic, area), and the filter stays E2's T1 call.

### Dependencies and licenses
- `uv add "av>=19.0.1" "numpy>=2.5.4"`. These are the current PyPI releases (checked 2026-10-16), and both require Python >=3.12, so rebase onto the ADR 0011 floor PR first.
- `THIRD_PARTY.md`, under Python libraries:
  - `| av (PyAV) | Probe and CPU decode | BSD-3-Clause; the FFmpeg bundled in its wheels is LGPL-3.0-or-later |`
  - `| numpy | Frame and audio arrays | BSD-3-Clause |`

### Tests
Added to `tests/unit/test_fixtures.py`:
- `test_warning_code_enum_matches_spec`: `{c.value for c in WarningCode} == spec_warning_codes()`

`tests/unit/test_media_types.py`:
- `test_stage_errors_round_trip_through_pickle`, parametrized over `ProbeError(UNREADABLE, "x")` and `DecodeError(PARTIAL_DECODE, "x")`. After the round trip, the type is the same, it is a `StageError`, `.warning` is equal, and `str()` is `"<CODE>: x"`.
- `test_asset_info_is_immutable`: `asset.duration_s = 1.0` raises `dataclasses.FrozenInstanceError`.
- `test_asset_info_normalizes_warnings`: built with `(B, A, B)`, where A sorts first, `.warnings == (A, B)`.
- `test_asset_info_keeps_unicode_path`: with `path=FIXTURES / "réunion 01.mp4"`, the pickle round trip is equal and `path.exists()` is true.
- `test_default_audio_rule`: no tracks gives None; no default flag gives `audio[0]`; a default flag on the second track gives the second track.
- `test_frame_pixels_are_read_only`: `frame.pixels[0, 0, 0] = 1` raises `ValueError`.
- `test_frame_requires_contiguous_pixels`: `Frame(0.0, np.rot90(a))` raises `ValueError`; `Frame(0.0, np.ascontiguousarray(np.rot90(a)))` works.
- `test_asset_warning_rejects_plain_str`: `AssetWarning("VFR_DETECTED", "x")` (with `# pyright: ignore[reportArgumentType]`) raises `TypeError`.
- `test_arrays_compare_by_identity`: `Frame` and `AudioChunk` instances built from equal arrays compare `False` without raising.
- `test_types_do_not_import_av`: a subprocess (`subprocess.run([sys.executable, "-c", ...], timeout=30)`) imports `tapesift.warning_codes` and `tapesift.media.types` and prints `'av' in sys.modules`. The output is `False`.
- `test_fake_decoder_satisfies_protocol`: a roughly 10-line `_FakeDecoder` is assigned to a `Decoder`-typed variable, and its first `Frame` has `pixels.dtype == np.uint8`.

pyright checks `tests/` in standard mode and `src/` in strict mode (`[tool.pyright] include`), so Protocol conformance is type-checked.

## Acceptance
| Command | Expected |
| --- | --- |
| `uv run python scripts/make_fixtures.py --only not_media.txt rotated_270.mp4` | lines beginning `ok` for `not_media.txt` (the build-time check that ffprobe rejects it) and `rotated_270.mp4` (rotation and pixel check); exit 0 |
| `ffprobe -v error tests/fixtures/not_media.txt; echo "exit=$?"` | an error message, then `exit=1` (non-zero) |
| `uv run pytest tests/unit/test_fixtures.py -q -k five_megabytes` | `1 passed`: the existing `test_fixtures_stay_under_five_megabytes` enforces the budget |
| `git status --short tests/fixtures` | exactly: ` M tests/fixtures/manifest.json`, `?? tests/fixtures/not_media.txt`, `?? tests/fixtures/rotated_270.mp4` |
| `uv run pytest tests/unit/test_fixtures.py tests/unit/test_media_types.py -q` | all pass |
| `uv run pytest -q -m "not gpu"` | all pass |
| `uv run python -c "from tapesift.warning_codes import WarningCode; print(len(WarningCode))"` | `17` |
| `uv run python -c "import sys, tapesift.media.types; print('av' in sys.modules)"` | `False` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff format --check .` | exit 0 |
| `uv run ruff check .` | `All checks passed!` |
| `uv lock --check` | exit 0 |
| `grep -c -e '"av>=19.0.1"' -e '"numpy>=2.5.4"' pyproject.toml` | `2` |
| `grep -c 'def iter_audio(self, asset: AssetInfo' docs/spec.md` | `1` |
| `grep -c 'def audio(self' docs/spec.md` | `0` |
| Command A1 below: a full-line, fixed-string grep for the exact UNREADABLE row | `1` |
| `grep -c 'When E1 adds the WarningCode enum' tests/unit/test_fixtures.py` | `0` |
| `grep -c 'test_warning_code_enum_matches_spec checks the WarningCode enum' tests/unit/test_fixtures.py` | `1` |
| `git diff --numstat main -- CHANGELOG.md` | `1	0	CHANGELOG.md` (one line added, none removed) |
| `grep -c -e '^. av ' -e '^. numpy ' THIRD_PARTY.md` | `2` |

Command A1 is kept out of the table because the row contains pipe characters:
```bash
grep -c -x -F '| Not a media file or unopenable (e.g. `.srt`, `.DS_Store` in a folder) | One stray file aborts a folder run | probe | Skip with the exact reason | `UNREADABLE` |' docs/spec.md
```

## Out of scope
- Probe, asset ID (E1) and decode (E2) implementations; E2's `rotated_270.mp4` pixel test
- `AudioTrack` (a whole track in memory): dropped
- `asset.license`: deferred to E5/L1 (output JSON)
- GPU frames, the NVDEC backend, tone mapping, deinterlacing; crop detection (C3)
- The schema mapper from these records to output JSON, and the JSON Schema (E5)
- Config keys: `config.py` does not exist yet (see the defaults card)
- A reusable fake decoder for pipeline tests: add it with the first pipeline test that needs one
- The "Python 3.11+" text in docs/spec.md (ADR 0011 PR)

## Risks
- **Merge order.** `uv add` of av 19 and numpy 2.5 fails while `requires-python` is `>=3.11`. M0 must merge after the ADR 0011 floor PR.
- **Fixture regeneration.** `make_fixtures.py` needs ffmpeg, ffprobe and espeak-ng on PATH, even with `--only`. The manifest's `ffmpeg` line is rewritten from the local FFmpeg; on anything other than 7.1.1, that line changes too. Note it in the PR.
- **E2 builds before E1 exists.** E2 tests construct `AssetInfo` literals by hand. Whichever merges second adds one `probe` → `iter_frames` test on `rotated.mp4`, `rotated_270.mp4`, `vfr.mp4` and `start_offset.mp4`.
- **Memory.** A 768 px RGB frame is about 1.7 MB, so `list(iter_frames(asset, None))` on a 3-hour file exhausts memory. Callers stream.
- **HDR_CONVERTED is emitted by probe.** E2's rgb24 output is 8-bit but not tone-mapped until that lands.
- **CHANGELOG.** M0, E1 and E2 each add a line under Unreleased and can conflict textually. Resolve at rebase by keeping all lines.

## Decision cards

### Decision (T3): pixel type of `Frame`
Context: Frame crosses every lane (the sampler, the Triton phash kernel, the VLM, the Embedder, which already uses `NDArray`) and worker processes.
Options: A. `NDArray[np.uint8]` (h, w, 3) RGB. B. PyAV `VideoFrame` (ties every lane to PyAV, does not pickle). C. torch tensor (makes torch a base dependency).
Hardest to reverse: every consumer's code.
**Decided 2026-10-16 (owner, after council):** A. Every `Frame` sets `pixels.flags.writeable = False`, because frozen does not protect array contents, and there is a test for it.
Revisit if: NVDEC profiling (v0.2) shows host copies dominate. Then add a GPU frame type behind the `gpu` extra.

### Decision (T3): records are frozen stdlib dataclasses
Context: These are pure data records, created per frame at volume. docs/spec.md reserves pydantic for config.
Options: A. `@dataclass(frozen=True, slots=True)`. B. pydantic models (a dependency, plus per-frame validation cost). C. TypedDict (mutable).
Hardest to reverse: E5's serialization.
**Decided 2026-10-16 (owner, after council):** A. E5 needs an explicit schema mapper, because `dataclasses.asdict` is not the schema shape. For example, `audio` is a tuple of streams in these records but `{codec, tracks, lang}` in the schema, `index` is internal, and `path` is a `Path`.
Revisit if: the mapper grows past about 50 lines.

### Decision (T3): `probe` is a plain function, not part of the Decoder Protocol
Context: Probing is backend-independent. Keeping it on Decoder would make E2 import E1's unbuilt code.
Options: A. `tapesift.media.probe.probe(path, *, full_hash=False)`. B. `Decoder.probe` delegating to E1.
Hardest to reverse: pipeline callers.
**Decided 2026-10-16 (owner, after council):** A. This PR updates the docs/spec.md block.
Revisit if: a backend needs its own metadata path (for example, a remote source).

### Decision (T3): audio streams as `Iterator[AudioChunk]`, with no `AudioTrack`
Context: A whole 3-hour track at 16 kHz is 691 MB of float32. `ASR.transcribe` already takes `Sequence[AudioChunk]`, and MULTI_AUDIO needs a track override.
Options: A. `iter_audio(..., track, chunk_s, warn)` yields chunks. B. `audio() -> AudioTrack`. C. Both.
Hardest to reverse: E3's VAD and ASR.
**Decided 2026-10-16 (owner, after council):** A. A "short gap" is at most `AUDIO_GAP_FILL_S` = 0.5 s and is zero-filled (R8). E3 must handle chunk seams, with VAD-aligned splits or overlap; a word can straddle a 600 s boundary.
Revisit if: E3 shows seams hurt WER even with overlap.

### Decision (T3): non-fatal decode problems go to a required `warn` callback
Context: "Keep partial results, record the gap", and a generator that raises cannot continue past a mid-file gap.
Options: A. Required keyword-only `warn: WarningSink`, and raise only before the first item. B. Raise after partial output. C. An iterator object with `.warnings`.
Hardest to reverse: every backend and every caller.
**Decided 2026-10-16 (owner, after council):** A. Consecutive failures coalesce: one `PARTIAL_DECODE` per gap run per stream, at most `MAX_GAP_WARNINGS` = 20 per call, then one summary warning (R10). Exceptions raised by `warn` propagate.
Revisit if: a non-streaming decode API appears.

### Decision (T3): new code `UNREADABLE` for files that cannot be opened as media
Context: Folders contain `.srt` and `.DS_Store` files. Calling those `PARTIAL_DECODE` would blur "decoded partially" with "nothing decoded".
Options: A. Reuse `PARTIAL_DECODE`. B. Add `UNREADABLE`, with a spec-table row and a fixture.
Hardest to reverse: codes users filter on. Adding a code is a schema minor bump.
**Decided 2026-10-16 (owner, after council):** B. M0 adds the enum member, the docs/spec.md row, `not_media.txt` and its manifest entry. `PARTIAL_DECODE` keeps the meaning "decoded partially".
Revisit if: users need finer reasons. Put those in `detail`, not in new codes.

### Decision (T3): meaning of the `asset` block fields
Context: These values are published in the output schema.
**Decided 2026-10-16 (owner, after council):**
- `w`/`h`: stored size; consumers swap them for rotation 90/270.
- `rotation`: counterclockwise degrees, equal to the display-matrix value mod 360 (R5). A 270-degree fixture, `rotated_270.mp4`, is added, with the pixel check owned by E2.
- Unknown values: `w`, `h` and `fps_avg` are None, and `codec` is `"unknown"`.
- `duration_s`: the video stream end when a video stream exists (audio is clipped to it), the default audio end for audio-only files, the container duration as fallback, else None (R3). `AV_LENGTH_MISMATCH` still fires.
- `audio.lang`: the default track's container tag.
Revisit if: E5's JSON Schema review or a user asks for display size.

### Decision needed (T2): defaults `MAX_SIDE_PX` 768, `sample_rate` 16 000, `chunk_s` 600, `SHORT_CLIP_S` 1.0, `AUDIO_GAP_FILL_S` 0.5, `MAX_GAP_WARNINGS` 20
Context: Pydantic config is meant to be the only home of defaults, but `config.py` does not exist. E1 and E2 need these values now.
Options:
- A. Keep them as module constants and Protocol defaults, each tied to a number already in the spec or decided above. `config.py` takes ownership when it lands.
- B. Required parameters with no defaults. Every test and fake must spell them out, and E1 and E2 still need shared thresholds.
- C. Create `config.py` now. That is Core's file.
Hardest to reverse: cheap. These are values, not shapes.
Recommendation: A.
Would change my mind: `config.py` lands before E1 and E2 merge.
Blocked until answered: nothing. Proceed with A unless overruled.

### Decision needed (T2): where `WarningCode` lives
Context: The codes cross every lane, so they do not belong under `media/`.
Options:
- A. `tapesift/warnings.py`. It shadows the stdlib name in importers.
- B. `tapesift/schema/warnings.py`. It creates E5's package early.
- C. `tapesift/warning_codes.py`.
Hardest to reverse: the import path.
Recommendation: C. Move it into `schema/` with a re-export if E5 wants it there.
Would change my mind: E5 settles on a `schema/` layout before this PR merges.
Blocked until answered: nothing. Proceed with C unless overruled.
