# 5. Probe and asset ID

Issue: #5   Lane: Media   Status: approved 2026-10-17 (owner, gate 1; all cards decided; values marked "verify with PyAV 19" may be corrected by the builder with evidence in the PR)
Amendments: 2026-10-17: NO_AUDIO expected on video-only fixtures (owner, card)

## Goal
After this lands, `tapesift.media.probe.probe(path, *, full_hash=False)` reads container metadata with PyAV and returns M0's `AssetInfo`. The result follows M0's rules R2-R4 and R11, carries the probe-owned warning codes with exact details for every fixture, and has a stable asset ID per D6. A file that is not media raises `ProbeError(UNREADABLE)`.

## Read first
- **docs/specs/4-media-types.md, the source of truth.** Read all of it, in particular:
  - the `warning_codes.py` and `types.py` blocks and E1's entry point;
  - Rules R2 (stream ends), R3 (`duration_s`), R4 (stream selection), R5 (rotation convention), R10 (decoders decide from the stream, never from `asset.warnings`; its early-EOF rule is E2's, and probe neither restates nor implements it) and R11 (thresholds);
  - "Which stage emits which code", and the cards on `asset` field meanings and `UNREADABLE`.
- docs/spec.md: backlog E1; Messy multimodal data (Detect column); Open decisions D6; Logging (`asset_id` and `stage` on every line)
- ADRs: 0006 (fixtures), 0008 (fixture tests only on the laptop), 0011 (Python 3.12 floor)
- Code: tests/fixtures/manifest.json, which after M0 includes `not_media.txt` and `rotated_270.mp4`. Also scripts/make_fixtures.py (the `check_*` functions show the metadata each case sets) and tests/unit/test_fixtures.py (the pattern for reading the manifest).
- PyAV 19.0.1 stubs, checked on GitHub at tag v19.0.1:
  - `av/stream.pyi`: `start_time`, `duration`, `time_base`, `disposition`, `language`, `average_rate`, `base_rate`. The rational attributes are `AVRational`, falsy `AVRational(0, 1)` when unset, never None.
  - `av/codec/context.pyi`: `coded_side_data -> dict[PktSideDataT, bytes]`, keyed `"display_matrix"`
  - `av/video/codeccontext.pyi`: `width`, `height`, `color_trc`, `field_order`
  - `av/container/core.pyi`: `av.open(..., timeout=)`
  - `av/container/input.py`: `codec_context` is None when FFmpeg has no decoder; `start_time` is None when unset, although the stub says `int`

## Scope
May change:
- `src/tapesift/media/probe.py` (new)
- `src/tapesift/media/asset_id.py` (new)
- `tests/unit/test_probe.py` (new)
- `tests/unit/test_asset_id.py` (new)
- `CHANGELOG.md`: one line under Unreleased, Added: "- `probe` reads media metadata into `AssetInfo` with warning codes; asset IDs are `tsid1:` (size, first and last 8 MiB) or, opt-in, `sha256:` of the whole file." Resolve conflicts at rebase by keeping all lines.

Must not touch:
- `pyproject.toml`, `uv.lock`, `THIRD_PARTY.md`. M0 adds `av>=19.0.1` and `numpy>=2.5.4`.
- `src/tapesift/warning_codes.py`, `src/tapesift/media/types.py`, `src/tapesift/media/__init__.py` (M0)
- `src/tapesift/media/decode.py` and its tests (E2)
- `scripts/make_fixtures.py`, `tests/fixtures/**`, `tests/unit/test_fixtures.py`
- `src/tapesift/cli/**`, `docs/**`, and everything else

## Interfaces touched
Both files are new. M0's types are used exactly as they are, with nothing redefined. The imports are:
- `from tapesift.warning_codes import AssetWarning, WarningCode`
- `from tapesift.media.types import AssetInfo, AudioStreamInfo, ProbeError, VideoInfo, MAX_SIDE_PX, SHORT_CLIP_S`
- `from av.stream import Disposition`

### `src/tapesift/media/asset_id.py` (stdlib only)
```python
SCHEME: Final = "tsid1"                  # scheme version; CHUNK_BYTES is part of it
CHUNK_BYTES: Final = 8 * 1024 * 1024     # 8 MiB

def asset_id(path: Path, *, full: bool = False) -> str:
    """See the reference implementation. Raises OSError if the file can't be read."""
```

The reference implementation (card 1, decided 2026-10-17; ADR 0012):
```python
def asset_id(path: Path, *, full: bool = False) -> str:
    size = path.stat().st_size
    with path.open("rb") as f:
        if full:                                       # plain sha256 of the file, == `shasum -a 256`
            return "sha256:" + hashlib.file_digest(f, "sha256").hexdigest()
        h = hashlib.sha256(size.to_bytes(8, "big"))
        h.update(f.read(CHUNK_BYTES))                  # head: bytes [0, min(size, 8 MiB))
        f.seek(max(CHUNK_BYTES, size - CHUNK_BYTES))   # tail never overlaps head
        h.update(f.read())                             # tail: empty when size <= 8 MiB
        return f"{SCHEME}:" + h.hexdigest()
```

Every file, small or large, hashes its size first. A file of 16 MiB or less therefore contributes its whole content once, and its default ID never equals its plain sha256. Every ID, in either mode, matches `^(tsid1|sha256):[0-9a-f]{64}$`: lowercase hex, 64 digits.

Default-mode hex vectors are not hand-written into this spec. The builder computes them with this reference implementation and pins them as literals in `test_asset_id.py`. Full-mode IDs need no computing: each is `"sha256:"` + the manifest `sha256`.

### `src/tapesift/media/probe.py`
```python
PROBE_TIMEOUT_S: Final = 30.0   # card 2; module constant until config.py exists
NVDEC_CODECS: Final = frozenset({"h264", "hevc", "av1", "vp8", "vp9", "mpeg1video",
                                 "mpeg2video", "mpeg4", "vc1", "mjpeg"})   # card 3

def probe(path: Path, *, full_hash: bool = False) -> AssetInfo:
    """Raises ProbeError(UNREADABLE, reason) when the file cannot be opened as media or has no
    audio or video stream. Never raises a PyAV exception."""
```

Private structural types. Each property is read-only, so real PyAV objects match covariantly. Probe reads only these attributes. Test stand-ins implement every one of them, so neither src nor tests need a `cast`.
```python
class _Rational(Protocol):              # av.AVRational; fractions.Fraction in stand-ins
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
    def coded_side_data(self) -> Mapping[PktSideDataT, bytes]: ...   # PktSideDataT from av.packet, under TYPE_CHECKING

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
    def codec_context(self) -> _CodecLike | None: ...   # None when FFmpeg has no decoder

class _VideoStreamLike(_StreamLike, Protocol):
    @property
    def codec_context(self) -> _VideoCodecLike | None: ...

class _ContainerLike(Protocol):
    @property
    def start_time(self) -> int | None: ...   # microseconds; the PyAV stub says int, runtime may be None
    @property
    def duration(self) -> int | None: ...     # microseconds

def _stream_start_s(stream: _StreamLike, container_start_s: float) -> float | None: ...
def _stream_end_s(stream: _StreamLike, container_start_s: float) -> float | None: ...
def _rotation_from_matrix(matrix: bytes | None) -> int: ...
def _select_video(videos: Sequence[_VideoStreamLike]) -> _VideoStreamLike | None: ...
```

Probe does not read `stream.type`. Streams come pre-split, in container order, from `container.streams.video` and `container.streams.audio`, and `_select_video` receives the video list.

What probe does:
1. **Open.** `with av.open(str(path), timeout=PROBE_TIMEOUT_S) as container:` holds every read, including the call to `asset_id(path, full=full_hash)`. So the container is closed on every path, including exceptions. Any `av.error.FFmpegError` or `OSError` raised inside becomes `ProbeError(WarningCode.UNREADABLE, f"{type(e).__name__}: {e.strerror or e}")`. That covers a missing path, a zero-byte file and a directory. The detail never contains the path. Nothing else is caught.
2. **Clock.**
   - `container_start_s = container.start_time / 1e6`, or 0.0 if that is None.
   - `tb = Fraction(time_base.numerator, time_base.denominator)`; it is unknown when `time_base` is falsy.
   - **Stream start:** `_stream_start_s = float(stream.start_time * tb) - container_start_s`. It is None when `start_time` is None or `tb` is unknown.
   - **Stream end (R2):** `_stream_end_s = float((stream.start_time + stream.duration) * tb) - container_start_s`. It is None when any of the three is missing.
   - All arithmetic is exact `Fraction`, converted to float last, so the 1.0 s fixtures do not land at 0.999…
3. **Select (R4).**
   - `_select_video` returns the first stream whose `disposition` lacks `Disposition.attached_pic`, or None.
   - Audio is `container.streams.audio`, in order.
   - If the selected video is None and there is no audio, probe raises `ProbeError(UNREADABLE, "no audio or video stream")`. That includes a file whose only video stream is cover art and which has no audio.
4. **Fill the records.**
   - `VideoInfo`:
     - `index`
     - `codec`: `codec_context.name`, or `"unknown"` when `codec_context` is None
     - `w`, `h`: from the codec context; None when there is no context or the value is 0
     - `fps_avg`: `float(average_rate)`, or None when it is falsy
     - `vfr`: **exactly the `VFR_DETECTED` condition from M0** (the row below). `vfr` is True if and only if probe emits `VFR_DETECTED`.
     - `rotation`: step 5
   - `AudioStreamInfo`: `index`, `codec` (same rule as video), `lang=stream.language`, `default=bool(stream.disposition & Disposition.default)`.
5. **Rotation (R5). The single source is `codec_context.coded_side_data.get("display_matrix")`. Probe decodes no frames.** If the value is absent, or there is no codec context, rotation is 0. `_rotation_from_matrix(data)`:
   - If `data` is None or not 36 bytes, the result is 0.
   - Otherwise `m = struct.unpack("=9i", data)`, `s0 = hypot(m[0], m[3])` and `s1 = hypot(m[1], m[4])`. If either is 0 (a zero-scale matrix), the result is 0.
   - Otherwise:
     1. **Angle:** `deg = -degrees(atan2(m[1] / s1, m[0] / s0))`, which is FFmpeg's `av_display_rotation_get`.
     2. **Normalize** to [0, 360): `deg = round(deg, 6) % 360`. The `round` absorbs float error, so -45 becomes exactly 315.0.
     3. **Round half up** to a multiple of 90: `k = floor(deg / 90 + 0.5)`.
     4. **Result:** `(k * 90) % 360`.
   - **Examples:** +45 → 45 → k = 1 → **90**. -45 → 315 → k = 4 → 360 % 360 → **0**. 180 → **180**. -90 → 270 → **270**.
   - A rotation of 0 never produces `ROTATED`.
6. **Duration (R3).**
   - With video: the video stream's end, else `container.duration / 1e6`, else None.
   - Audio-only: the default audio stream's end, else the container duration, else None.
7. **Warnings.** Probe emits the warnings below. `AssetInfo.__post_init__` sorts them and deduplicates them by (code, detail).
8. **Log.** One record at DEBUG through `logging.getLogger(__name__)` (`tapesift.media.probe`): message `"probed"`, with `extra={"asset_id": info.id, "stage": "probe"}`. No subprocess calls.

### Probe-owned codes and exact details
These rows follow M0's emitter table. The R11 rules are M0's; the rows marked **T1** are E1's calls, to be listed in the PR.

In the format strings below:
- `v` is the selected video stream's index, and `a` is `default_audio.index`.
- Floats use `.2f`.
- `fo` maps `field_order` {2: "tt", 3: "bb", 4: "tb", 5: "bt"}.
- `trc` maps `color_trc` {16: "PQ", 18: "HLG"}.

| Code | Rule | Detail (exact) |
| --- | --- | --- |
| `UNREADABLE` | raised as `ProbeError` (steps 1 and 3), never placed in `warnings` | `f"{type(e).__name__}: {e.strerror or e}"`, or `"no audio or video stream"` |
| `VFR_DETECTED` | **T1:** `average_rate` and `base_rate` are both truthy and `abs(avg - base) / base > 0.01` | `f"video stream {v}: average {avg:.2f} fps vs nominal {base:.2f} fps; times from PTS"` |
| `ROTATED` | `video.rotation != 0` | `f"video stream {v}: display matrix rotation {rotation} deg"` |
| `START_OFFSET` | **T1:** `abs(start) > 0.25` s for the selected video stream, the default audio stream, or both, using the stream start from step 2. A -0.4 s start is flagged; a stream with an unknown start is ignored. Probe emits **one** warning naming every offending stream, video first, with parts joined by `"; "`. | each part is `f"{kind} stream {i} starts at {start:.2f} s"`, where `kind` is `video` or `audio` |
| `AV_LENGTH_MISMATCH` | **T1:** the R2 ends of video and default audio are both known and differ by more than 1.0 s | `f"video stream {v} ends at {ve:.2f} s, audio stream {a} ends at {ae:.2f} s"` |
| `NO_AUDIO` | `video is not None and not audio` | `"no audio stream; ASR skipped"` |
| `MULTI_AUDIO` | `len(audio) >= 2` | `f"{len(audio)} audio streams; default is stream {a}"` |
| `INTERLACED` | R11: `field_order` in 2..5 | `f"video stream {v}: field order {fo}; not deinterlaced"` |
| `HDR_CONVERTED` | R11: `color_trc` in {16, 18} | `f"video stream {v}: {trc} transfer; decoded to 8-bit, not tone-mapped"` |
| `SHORT_CLIP` | R11: `duration_s is not None and duration_s < SHORT_CLIP_S` | `f"duration {duration_s:.2f} s"` |
| `DOWNSCALED` | R11: `w` and `h` are known and `max(w, h) > MAX_SIDE_PX` | `f"video stream {v}: {w}x{h} downscaled to {MAX_SIDE_PX} px long side"` |
| `UNSUPPORTED_CODEC` | At most one warning per stream, checked on the selected video stream and on every audio stream. (a) No decoder (`codec_context is None`). (b) Video only: the codec is not in `NVDEC_CODECS` (card 3). **(b) is skipped for any stream where (a) applies.** Under R10, (b) never stops a CPU decode. | (a) `f"stream {index} codec {name}: no decoder"`, where `name` is `"unknown"`; (b) `f"stream {index} codec {name}: no NVDEC, CPU decode"` |

Not emitted by probe, per M0's table: `PARTIAL_DECODE` (E2), `CROPPED` (C3), `LOW_SPEECH` (E3), `MEDIA_TEXT` (E4), `DUPLICATE` (E7, which compares `AssetInfo.id`).

## Acceptance
Pre-condition: M0 (#4) is merged. That brings `av` 19.0.1, numpy, and the 25-entry manifest including `not_media.txt` and `rotated_270.mp4`.

`M` below means the number of tests collected on `main` before this branch, from `uv run pytest -q -m "not gpu" --collect-only | tail -1`. `F` means the number of files `ruff format --check .` reports on `main`.

| Command | Expected last line |
| --- | --- |
| `uv run pytest tests/unit/test_asset_id.py -q` | `66 passed` |
| `uv run pytest tests/unit/test_probe.py -q` | `82 passed` (`81 passed` if the cover-art mux test was dropped, see below) |
| `uv run pytest tests/unit/test_fixtures.py tests/unit/test_media_types.py -q` | the same count as on `main` (both files untouched) |
| `uv run pytest -q -m "not gpu"` | `M + 148 passed` (`M + 147` without the cover-art test); no `failed`, `error` or `skipped` |
| `uv run ruff format --check .` | `F + 4 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `git diff --numstat main -- CHANGELOG.md` | `1	0	CHANGELOG.md` |

`git diff --name-only main...HEAD` prints exactly these lines:
```text
CHANGELOG.md
src/tapesift/media/asset_id.py
src/tapesift/media/probe.py
tests/unit/test_asset_id.py
tests/unit/test_probe.py
```

No subprocess calls, and no skips in the new tests. Each command below prints nothing (exit 1):
```bash
grep -nE "subprocess|Popen|os\.system" src/tapesift/media/probe.py src/tapesift/media/asset_id.py
grep -nE "pytest\.skip|mark\.skip|importorskip|mark\.xfail" tests/unit/test_probe.py tests/unit/test_asset_id.py
```

All synthetic test data is `(bytes(range(251)) * k)[:n]`, with `k = n // 251 + 1`, written to `tmp_path`.

### `test_asset_id.py`: 66 tests

| Test | Count | Asserts |
| --- | --- | --- |
| `test_full_id_matches_manifest[<fixture>]` | 25 | `asset_id(p, full=True) == "sha256:" + entry["sha256"]` and the ID matches `^(tsid1\|sha256):[0-9a-f]{64}$` |
| `test_default_id_shape[<fixture>]` | 25 | the ID matches `^(tsid1\|sha256):[0-9a-f]{64}$`, starts with `"tsid1:"`, and is not equal to `"tsid1:" + entry["sha256"]` |
| `test_pinned_fixture_vectors` | 1 | `asset_id(clean.mp4)` and `asset_id(réunion 01.mp4)` equal literals the builder pinned from the reference implementation |
| `test_pinned_40mib_vector` | 1 | the default ID of the 40 MiB pattern file equals a pinned literal |
| `test_duplicate_ids_match` | 1 | `asset_id(clean.mp4) == asset_id(clean_copy.mp4)` (E7's `DUPLICATE` signal) |
| `test_boundary_sizes[n]` | 6 | for n in 0, 1, 8 MiB, 8 MiB + 1, 16 MiB, 16 MiB + 1, the ID equals `"tsid1:" + sha256(n.to_bytes(8, "big") + d[:8 MiB] + d[max(8 MiB, n - 8 MiB):])`, computed in the test |
| `test_middle_byte_collides` | 1 | on the 40 MiB file, flipping the byte at 20 MiB keeps the default ID and changes the full ID (the documented collision) |
| `test_sensitive_bytes[case]` | 5 | flipping byte 0, byte 8 MiB - 1, byte size - 8 MiB or the last byte, or appending one byte, changes the default ID |
| `test_sparse_1gib` | 1 | a 1 GiB sparse file (`truncate`) matches the independent size, head and tail computation |

### `test_probe.py`: 82 tests
Stand-ins: `_FakeStream` and `_FakeCodec` implement every property of `_VideoStreamLike` / `_StreamLike` and `_VideoCodecLike`:
- `time_base`, `average_rate` and `base_rate` are `fractions.Fraction`;
- `disposition` uses the real flags, `Disposition.default`, `Disposition.attached_pic` and `Disposition(0)`;
- `coded_side_data` is a `dict`.

`_FakeContainer` has `streams.video`, `streams.audio`, `start_time`, `duration`, `__enter__`, `__exit__` and `close`. Probe-level stand-in tests monkeypatch `tapesift.media.probe.av.open` to return it, and use a real pattern file in `tmp_path` as the path, so `asset_id` still runs.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_manifest_codes[<fixture>]` | 25 | An `UNREADABLE` entry raises `ProbeError` with `.warning.code == UNREADABLE`. Otherwise `sorted(w.code for w in probe(p).warnings) == sorted(set(entry["warning_codes"]) & PROBE_CODES | ({NO_AUDIO} if name in VIDEO_ONLY else set()))`, and `(not info.audio) == (name in VIDEO_ONLY)`. `VIDEO_ONLY` is the 12 fixtures with a video stream and no audio stream (the manifest lists only the case each was built for). Lists are compared, not sets, so a doubled `UNSUPPORTED_CODEC` on unknown_codec.mov fails. The per-fixture expectations are in the table below. |
| `test_fixture_detail[<case>]` | 13 | the exact (code, detail) pair on a fixture, from the list below |
| `test_unreadable_detail[<case>]` | 2 | `not_media.txt` gives `"InvalidDataError: Invalid data found when processing input"`; a missing path gives `"FileNotFoundError: No such file or directory"` |
| `test_standin_detail[<case>]` | 4 | the exact (code, detail) pairs from stand-ins, listed below |
| `test_code_coverage` | 1 | `PROBE_CODES \| {UNREADABLE} \| {PARTIAL_DECODE, CROPPED, LOW_SPEECH, MEDIA_TEXT, DUPLICATE} == set(WarningCode)`, and the sets are disjoint |
| `test_duration_s[<fixture>]` | 7 | R3, within 0.01: clean.mp4 5.0, av_mismatch.mp4 3.0, start_offset.mp4 5.52, no_audio.mp4 3.0, music.m4a 6.0, hdr10.mkv 2.0 (the stream duration is None, so the container duration), uhd_4k.mp4 exactly 1.0 |
| `test_stream_clock[<case>]` | 5 | `_stream_start_s` / `_stream_end_s` on a `_FakeStream` with `time_base=Fraction(1, 1000)`: `start_time=None` gives (None, None); `duration=None` gives (start, None); `time_base=Fraction(0)` gives (None, None); `(1520, 4000)` with `container_start_s=0.0` gives (1.52, 5.52); `(0, 3000)` with `container_start_s=-0.064` gives (0.064, 3.064) |
| `test_r4_fixture_indexes[<fixture>]` | 2 | multi_audio.mkv: `video.index == 0`, `[a.index for a in audio] == [1, 2]`, `default_audio.index == 1`. music.m4a: `video is None`, `audio[0].index == 0`. |
| `test_select_video_skips_cover_art[<case>]` | 2 | `[video(attached_pic), video(plain)]` returns the second; `[video(attached_pic)]` returns None |
| `test_cover_art_m4a_in_process` | 1 | an m4a muxed in-process by PyAV into `tmp_path` (AAC silence, plus one mjpeg or png stream with `Disposition.attached_pic` and one packet) probes with `video is None` and one audio stream |
| `test_rotation_from_matrix[<case>]` | 10 | None → 0; 35 bytes → 0; all-zero (zero scale) → 0; identity → 0; `(0, -65536, 0, 65536, 0, 0, 0, 0, 1 << 30)` → 90; `(0, 65536, 0, -65536, 0, 0, 0, 0, 1 << 30)` → 270; `(-65536, 0, 0, 0, -65536, 0, 0, 0, 1 << 30)` → 180; `(46341, -46341, 0, 46341, 46341, 0, 0, 0, 1 << 30)` (+45) → 90; `(46341, 46341, 0, -46341, 46341, 0, 0, 0, 1 << 30)` (-45 = 315) → 0; `(47143, -45525, 0, 45525, 47143, 0, 0, 0, 1 << 30)` (+44) → 0 |
| `test_unicode_path[<case>]` | 2 | `probe(FIXTURES / "réunion 01.mp4").path` equals the input path; a copy at `tmp_path / "dossier é" / "réunion 01.mp4"` probes with no warnings |
| `test_bad_input_unreadable[<case>]` | 3 | a missing path, a zero-byte `tmp_path / "empty.mp4"` and a directory `tmp_path / "folder.mp4"` each raise `ProbeError` with code `UNREADABLE`; no `av.error.*` or `OSError` escapes |
| `test_container_closed[<case>]` | 2 | `av.open` is monkeypatched to return a spy that wraps the real container, delegates attribute reads, and records each `__exit__` call before calling the real `__exit__`. The spy's `__exit__` is called exactly once both after a successful probe of clean.mp4 and after a `ProbeError` caused by monkeypatching `tapesift.media.probe.asset_id` to raise `OSError`. |
| `test_timeout_passed` | 1 | the `av.open` spy records `timeout == PROBE_TIMEOUT_S` |
| `test_full_hash_id` | 1 | `probe(clean.mp4, full_hash=True).id == "sha256:" + manifest["clean.mp4"]["sha256"]`; without `full_hash`, the ID starts with `"tsid1:"` |
| `test_log_extras` | 1 | with `caplog.at_level(logging.DEBUG, logger="tapesift.media.probe")`, probing clean.mp4 leaves one record from that logger with `record.asset_id == info.id` and `record.stage == "probe"` |

Per-fixture expectations for `test_manifest_codes`:

| Fixture | probe gives | Manifest codes owned elsewhere |
| --- | --- | --- |
| clean.mp4, speech.mp4, réunion 01.mp4 | no codes | none |
| long_3h.mp4 | NO_AUDIO (video only) | none |
| vfr.mp4 | VFR_DETECTED, NO_AUDIO, and `video.vfr is True` | none |
| rotated.mp4 | ROTATED, `rotation == 90` | none |
| rotated_270.mp4 | ROTATED, NO_AUDIO, `rotation == 270`, `w == 320`, `h == 240` (stored size) | none |
| start_offset.mp4 | START_OFFSET | none |
| av_mismatch.mp4 | AV_LENGTH_MISMATCH | none |
| no_audio.mp4 | NO_AUDIO | none |
| multi_audio.mkv | MULTI_AUDIO only: **no START_OFFSET** (0.064 s) and no AV_LENGTH_MISMATCH (stream ends unknown) | none |
| prores.mov | UNSUPPORTED_CODEC, NO_AUDIO | none |
| unknown_codec.mov | exactly one UNSUPPORTED_CODEC ((a), with (b) skipped), NO_AUDIO, `video.codec == "unknown"` | none |
| interlaced.mp4 | INTERLACED, NO_AUDIO | none |
| hdr10.mkv | HDR_CONVERTED, NO_AUDIO | none |
| short_clip.mp4 | SHORT_CLIP | none |
| uhd_4k.mp4 | DOWNSCALED, NO_AUDIO | none |
| not_media.txt | raises `ProbeError(UNREADABLE)` | none |
| silence.mp4, music.m4a | no codes | LOW_SPEECH (E3) |
| truncated.mp4 | no codes, no exception | PARTIAL_DECODE (E2) |
| letterbox.mp4, pillarbox.mp4 | NO_AUDIO (video only) | CROPPED (C3) |
| clean_copy.mp4 | no codes, same `id` as clean.mp4 | DUPLICATE (E7) |
| burned_text.mp4 | NO_AUDIO (video only) | MEDIA_TEXT (E4) |

`test_fixture_detail`: the 13 exact pairs. Together with `test_unreadable_detail` and `test_standin_detail`, every code probe emits, all 11 plus `UNREADABLE`, has at least one pinned (code, detail) pair.

| Fixture | Code | Detail |
| --- | --- | --- |
| vfr.mp4 | VFR_DETECTED | `video stream 0: average 16.85 fps vs nominal 30.00 fps; times from PTS` |
| rotated.mp4 | ROTATED | `video stream 0: display matrix rotation 90 deg` |
| rotated_270.mp4 | ROTATED | `video stream 0: display matrix rotation 270 deg` |
| start_offset.mp4 | START_OFFSET | `video stream 0 starts at 1.52 s` |
| av_mismatch.mp4 | AV_LENGTH_MISMATCH | `video stream 0 ends at 3.00 s, audio stream 1 ends at 6.00 s` |
| no_audio.mp4 | NO_AUDIO | `no audio stream; ASR skipped` |
| multi_audio.mkv | MULTI_AUDIO | `2 audio streams; default is stream 1` |
| interlaced.mp4 | INTERLACED | `video stream 0: field order tt; not deinterlaced` |
| hdr10.mkv | HDR_CONVERTED | `video stream 0: PQ transfer; decoded to 8-bit, not tone-mapped` |
| short_clip.mp4 | SHORT_CLIP | `duration 0.40 s` |
| uhd_4k.mp4 | DOWNSCALED | `video stream 0: 3840x2160 downscaled to 768 px long side` |
| unknown_codec.mov | UNSUPPORTED_CODEC | `stream 0 codec unknown: no decoder` |
| prores.mov | UNSUPPORTED_CODEC | `stream 0 codec prores: no NVDEC, CPU decode` |

`test_standin_detail`: 4 pairs, run through `probe` with `_FakeContainer`:

| Stand-in | Code | Detail |
| --- | --- | --- |
| h264 video stream 0 starting at 1.0 s; default audio stream 1 starting at -0.4 s (the multi-stream join and a negative start) | START_OFFSET | `video stream 0 starts at 1.00 s; audio stream 1 starts at -0.40 s` |
| h264 video stream 0; audio stream 1 with `codec_context=None` | UNSUPPORTED_CODEC | `stream 1 codec unknown: no decoder` |
| no video and no audio streams | UNREADABLE (raised) | `no audio or video stream` |
| one video stream with `Disposition.attached_pic` and no audio (cover art only) | UNREADABLE (raised) | `no audio or video stream` |

**If PyAV 19 cannot mux an attached picture in-process,** the builder deletes `test_cover_art_m4a_in_process` rather than skipping it. The R4 logic stays covered by `test_select_video_skips_cover_art` and the cover-art stand-in. The builder then files a follow-up issue, "cover_art.m4a fixture via scripts/make_fixtures.py" (Media lane), and links it in the PR. No `pytest.skip` appears anywhere.

## Out of scope
- A config key or CLI flag for `full_hash` or the timeout (Core lane, once `config.py` exists)
- Frame and audio decode, applying rotation, deinterlace, tone mapping and downscale (E2 and the follow-ups); R10's early-EOF rule (E2)
- The codes owned elsewhere: PARTIAL_DECODE, CROPPED, LOW_SPEECH, MEDIA_TEXT, DUPLICATE
- Mapping `AssetInfo` to output JSON (E5)
- Caching IDs by mtime. Add it if profiling shows hashing cost.
- Writing ADR 0012 for the asset ID (Docs lane or owner, from card 1)
- A committed cover-art fixture (the follow-up issue above, only if the in-process test is impossible)
- **Follow-up for E7:** before emitting `DUPLICATE` on two equal `tsid1:` IDs, E7 confirms the match with a full hash of both files (card 1).
- M0's `AssetInfo.id` comment (`tsid1:` / `sha256:`), which M0's planner is amending. E1 references it and does not edit `types.py`.

## Risks
- **Rotation source.** It relies on FFmpeg's `avcodec_parameters_to_context` copying the stream's `coded_side_data`, which PyAV 19 exposes. If `display_matrix` is missing on rotated.mp4 or rotated_270.mp4, stop and report. Do not add a decode fallback; probe decodes no frames.
- **Rotation sign.** If rotated_270.mp4 comes back as 90, stop and report; do not flip the sign. R5 and E2's pixel test depend on this value.
- **Structural typing.** If pyright strict does not accept real PyAV streams or containers as the private Protocols, for example over `coded_side_data`'s key type, adjust the Protocol, never add a `cast`. If that fails twice, raise it.
- **FFmpeg versions.** The fixtures were made with FFmpeg 7.1.1, and PyAV 19 bundles a newer FFmpeg. Pinned numbers may differ: vfr.mp4's 16.85 fps, start_offset's 1.52 s, the mkv durations, and FFmpeg's error strings in `test_unreadable_detail`.
  - Retune the three T1 thresholds, never the fixtures or M0's R11.
  - If a pinned detail moves, report it with the observed value rather than loosening the test.
- **VFR from metadata alone** misses phone video whose average rate is within 1% of the nominal rate. Times stay correct because E2 uses PTS. Mark it with a `ponytail:` comment. Upgrade path: scan PTS gaps over the first N packets.
- **AV_LENGTH_MISMATCH** is skipped when stream ends are unknown, which is typical for MKV and WebM. Mark it with a `ponytail:` comment.
- **The static NVDEC set ages.** AV1 on pre-Ampere GPUs is not flagged; the future GPU backend still falls back on its own (R10).
- **Display-matrix flips** (a negative determinant) are ignored; only the rotation is read.
- **The timeout bounds I/O only.** It covers I/O inside libavformat (open, find_stream_info), not CPU work. Probe does no decoding, so there is no unbounded CPU work.
- **Unicode normalization.** On macOS, `réunion` may arrive NFC or NFD. Build paths from manifest names with pathlib and never re-encode them.

## Decision cards

### Decision (T3): asset ID scheme (D6; ADR 0012)
**Decided 2026-10-17 (owner, after council); ADR 0012:** option A as written below.
**Context.** D6 says "sha256 of size + first and last 8 MB; full hash opt-in; the collision risk is written down". IDs key resume (E7), `DUPLICATE`, `--asset ID` and `purge ASSET`, so any choice is hard to undo. M0's planner is amending the `AssetInfo.id` comment to `tsid1:` / `sha256:` to match.

**The decided scheme (the reference implementation above).**
- **Default ID:** `"tsid1:" + sha256(size as 8-byte big-endian ‖ first 8 MiB ‖ bytes from max(8 MiB, size − 8 MiB) to the end)`. The head and tail never overlap, so a file of 16 MiB or less contributes its whole content once.
- **Versioning:** `tsid1` is the scheme version, and the 8 MiB chunk size is part of that version. Any change to the layout or the chunk size means `tsid2`.
- **Full mode:** `"sha256:" + sha256(file)`, the plain digest, so `shasum -a 256` verifies it. No `sha256-full:` prefix exists anywhere.
- **Indexes must not mix modes.** The two prefixes never compare equal, so a mode switch re-indexes everything. `tapesift` should refuse, or at least warn, when an index already holds the other prefix; that check belongs to E7.
- **E7 confirms every `DUPLICATE`** with a full hash of both files before emitting it. That makes the collision below cost one extra full read, instead of a silently skipped file. Logged as an E7 follow-up.

**Options considered.**
- **A. `tsid1:` default and `sha256:` full.** This is the recommendation. Pros: `sha256:` always means a true file sha256; the scheme can be versioned; the mode shows in the ID. Cons: departs from the schema's `"sha256:9f2c..."` example, which now describes full mode; M0's comment needs a one-line update.
- **B. `sha256:` default and `sha256-full:` full** (my earlier draft, and M0's comment). Pros: matches the current example. Cons: a `sha256:` ID that is not the file's sha256 misleads; there is no version for a future change.
- **C. No prefix distinction between modes.** Cons: IDs from different modes look alike; resume silently re-indexes.

**Collision risk, written down.** Two files of the same size, larger than 16 MiB, with identical first and last 8 MiB but different middles, get the same default ID. Realistic case: two fixed-bitrate recordings of equal length (PCM WAV, broadcast captures) that open and close with about 45 s of identical silence or bars. E7's full-hash confirmation keeps them from being merged. Full mode removes the risk at the cost of reading every file whole.

**Hardest to reverse.** Any choice, once v0.1 indexes exist. `tsid1` keeps the next change cheap.

**Recommendation.** A. Accepted. The ADR 0012 file is written by the Docs lane or the owner; this spec can't touch docs/.

**Would change my mind.** The owner wants the schema example kept literally as `sha256:` for default IDs.

**Blocked until answered.** Nothing. Decided.

### Decision (T2): `PROBE_TIMEOUT_S = 30.0` as a module constant
**Decided 2026-10-17 (owner):** A.
**Context.** AGENTS.md requires a timeout on every network or subprocess call. Probe reads local files in-process, but media libraries often sit on NAS or SMB mounts, where an open can hang. PyAV applies `av.open(timeout=)` to open and find_stream_info I/O through FFmpeg's interrupt callback. `config.py` does not exist yet; M0's defaults card set the precedent of module constants until it does.

**Options.**
- **A. A module constant of 30.0 s, which becomes a config default when `config.py` lands.** Pros: bounded today, with no new config key. Cons: users can't tune it yet.
- **B. A `timeout_s` parameter on `probe`.** Cons: it changes M0's fixed signature.
- **C. No timeout, since the files are local.** Cons: a hung mount stalls a folder run forever; breaks the AGENTS.md rule in spirit.

**Hardest to reverse.** B: it changes a signature.

**Recommendation.** A.

**Would change my mind.** Real NAS runs where a healthy open takes more than 30 s.

**Blocked until answered.** Nothing. Decided.

### Decision (T2): what probe's `UNSUPPORTED_CODEC` means for ProRes on a CPU-only machine
**Decided 2026-10-17 (owner):** A, the fixed no-NVDEC codec list.
**Context.** The manifest expects `UNSUPPORTED_CODEC` on prores.mov ("ProRes: no NVDEC, CPU fallback"). M0's emitter table defers the meaning to this card. PyAV decodes ProRes on any CPU, so a check against the real machine would emit nothing on laptops and CI, and the fixture test would depend on hardware. R10 already ensures that probe's entry never stops a CPU decode.

**Options.**
- **A. A static NVDEC codec set in probe** (rule (b)), with the details `": no decoder"` and `": no NVDEC, CPU decode"` telling the two cases apart. Pros: deterministic; the manifest passes everywhere. Cons: CPU-only users see a code for a file that decodes fine; one code covers two severities.
- **B. Check the real machine in the future GPU backend**, and make the prores manifest entry conditional. Pros: accurate. Cons: changes fixture expectations, which are outside these paths; E1's acceptance can't pass.
- **C. A separate `CPU_FALLBACK` code.** Pros: precise. Cons: changes M0's enum, the spec table, the manifest and the schema.

**Hardest to reverse.** C: it changes the schema.

**Recommendation.** A.

**Would change my mind.** Users read the code on CPU as an error; then C at the next minor schema bump.

**Blocked until answered.** Nothing. Decided.
