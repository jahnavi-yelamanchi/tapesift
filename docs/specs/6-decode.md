# 6. CPU decode with PyAV (E2)

Issue: #6   Lane: Media   Status: approved 2026-10-17 (owner, gate 1; all cards decided; values marked "verify with PyAV 19" may be corrected by the builder with evidence in the PR)

## Goal
`tapesift.media.decode.PyAVDecoder` implements M0's `Decoder` Protocol on the CPU:
- `iter_frames` streams frames timed from PTS, upright, and no larger than `MAX_SIDE_PX`.
- `iter_audio` streams 16 kHz mono float32 `AudioChunk`s.

Both follow M0's rules R1 and R5-R10, including the amended R10 early-EOF rule, and report damaged media through `warn` instead of raising. Per docs/spec.md's Engineering standards ("timestamp math is pure"), all the R1/R6/R7/R8/R10 arithmetic lives in pure functions that are tested directly.

## Read first
- **docs/specs/4-media-types.md, in full,** including the R10 early-EOF amendment (`EARLY_EOF_S`). It is the source of truth. This spec says how E2 implements M0's rules, which choices M0 leaves to E2 (marked T1), and what the lead decided on points M0 leaves open (marked "ruling"). It never restates a rule differently. Where the two disagree, M0 wins.
- docs/spec.md: "Messy multimodal data", Engineering standards (pure timestamp math, hypothesis), backlog E2.
- ADRs: 0006 (committed fixtures), 0008 (fixture smoke tests run on the laptop), 0011 (Python 3.12 floor).
- Code (M0, on main before E2 builds): `src/tapesift/media/types.py`, `src/tapesift/warning_codes.py`, `tests/unit/test_media_types.py` (test house style), `tests/fixtures/manifest.json`, `scripts/make_fixtures.py`.
- PyAV 19.0.1 (pinned by M0), checked in the v19.0.1 source:
  - `av/container/input.py`:
    - `av.open` runs `avformat_find_stream_info`.
    - It then sets `stream.codec_context = None` for any stream whose `avcodec_find_decoder` returns NULL, and does not raise. The stub types it as non-optional.
  - `container.start_time` is in microseconds, or None.
  - `VideoFrame.to_ndarray(**kw)` forwards to `reformat(width, height, format, interpolation, ...)`.
  - `VideoFrame.from_ndarray(arr, format="rgb24")`.
  - `av.video.reformatter.Interpolation.AREA`.
  - `av.AudioResampler(format, layout, rate).resample(frame | None) -> list[AudioFrame]`. `None` flushes it. It is a filter graph, so output frames carry `pts` and `time_base`.
  - `av.FFmpegError` is the base of every FFmpeg error class.

## Scope
May change:
- `src/tapesift/media/decode.py` (new)
- `tests/smoke/test_decode.py` (new). Every decode test lives here, pure-function tests included: one module, one test file.
  - Why `tests/smoke/`: most of these tests open real fixtures with real FFmpeg and include two 3-hour passes, which is ADR 0008's "fixture smoke test". Keeping them out of `tests/unit` keeps `pytest tests/unit -x -q` fast.
  - The pure tests take milliseconds.
  - `make smoke` (`uv run pytest tests/smoke -q`) already targets this directory, and `make test`/`make check` run it in CI.
- `tests/smoke/conftest.py` (new):
  - `FIXTURES: Path = Path(__file__).parents[1] / "fixtures"`;
  - a session-scoped `manifest` fixture returning `json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))`.
- `CHANGELOG.md`: one line under Unreleased, Added: `- CPU decode with PyAV: PTS-timed, upright, downscaled frames and 16 kHz mono audio chunks (#6).`

Must not touch:
- `pyproject.toml`, `uv.lock`, `THIRD_PARTY.md`. M0 added av and numpy; hypothesis is already a dev dependency.
- `src/tapesift/media/types.py`, `src/tapesift/media/__init__.py`, `src/tapesift/warning_codes.py` (M0). Anything missing there means a card, not an edit.
- `src/tapesift/media/probe.py`, `src/tapesift/media/asset_id.py`, and E1's tests
- `tests/smoke/test_probe_decode.py`. That is the lead's follow-up (see Out of scope).
- `scripts/make_fixtures.py`, `tests/fixtures/`, `tests/unit/test_fixtures.py`, `docs/spec.md`

## Interfaces touched
Before: none.

After: `src/tapesift/media/decode.py`. `PyAVDecoder` is the decoder. The pure functions below are module-level and not re-exported from `tapesift.media`; tests import them directly. Constants come from `tapesift.media.types` (`MAX_SIDE_PX`, `AUDIO_GAP_FILL_S`, `MAX_GAP_WARNINGS`, `EARLY_EOF_S`) and are never redefined. `decode.py` calls PyAV as `av.open(...)` through the module, so tests can patch `av.open`.

```python
class PyAVDecoder:
    """M0's Decoder on the CPU via PyAV. Stateless; one instance serves any number of assets."""

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


# ---- pure timestamp math (no I/O, no PyAV objects) ----

def half_up(x: float) -> int:
    """math.floor(x + 0.5). The only rounding used in this module; round() is never used."""

def clock_s(pts: int, time_base: Fraction, container_start_s: float) -> float:
    """R1 step 1: float(pts * time_base) - container_start_s."""

def frame_kept(t_s: float, duration_s: float | None, last_t_s: float | None) -> bool:
    """R1 steps 2-3 and R7 step 2: t_s >= 0, t_s < duration_s when known, t_s > last_t_s when known."""

def window_index(t_s: float, every_s: float) -> int:
    """R7 step 3: floor(t_s / every_s + 1e-9)."""

def upright_size(h: int, w: int) -> tuple[int, int]:
    """R6 on an upright (h, w): unchanged when max(h, w) <= MAX_SIDE_PX; else each side becomes
    max(1, half_up(side * MAX_SIDE_PX / max(h, w)))."""

@dataclass(frozen=True, slots=True)
class Placement:
    new_run: bool   # start a new run at start_s (flushes the pending chunk)
    start_s: float  # container-clock time of the first kept sample
    fill: int       # zeros written before the kept samples; always 0 when new_run
    skip: int       # leading samples dropped (overlap with the run, or t < 0)
    keep: int       # samples kept after skip; samples at or past duration_s are cut

def place_audio(
    t_s: float | None, n: int, *, sample_rate: int,
    run_end_s: float | None, duration_s: float | None,
) -> Placement:
    """R1 steps 2-3 and R8 for one resampled frame of n samples whose first sample is at t_s."""

def chunk_runs(
    pieces: Iterable[tuple[bool, float, NDArray[np.float32]]], *, chunk_n: int, sample_rate: int,
) -> Iterator[AudioChunk]:
    """R8 chunking of (new_run, start_s, samples) pieces, zero fill already prepended.
    An empty new_run piece still starts a new run at its start_s; an empty continuing piece is
    a no-op. Never yields an empty chunk."""

@dataclass(frozen=True, slots=True)
class GapState:
    last_good_end_s: float = 0.0      # `a` for the next run (R10)
    open_from_s: float | None = None  # `a` of the open run; None when no run is open

def gap_on_good(state: GapState, start_s: float, end_s: float) -> tuple[GapState, tuple[float, float] | None]:
    """A good item. Closes an open run at start_s and returns that run's raw (a, b)."""

def gap_on_fail(state: GapState) -> GapState:
    """A failed item. Opens a run at last_good_end_s if none is open; otherwise a no-op."""

def gap_on_eof(state: GapState, duration_s: float | None) -> tuple[float, float | None] | None:
    """R10 at EOF (amended). If a run is open, close it at duration_s (None as b means "end").
    If no run is open, i.e. the stream's last decode step was clean, and duration_s is not None
    and state.last_good_end_s < duration_s - EARLY_EOF_S, return the early-EOF run
    (last_good_end_s, duration_s). Earlier closed runs don't matter. Otherwise None."""

def clamp_run(run: tuple[float, float | None], duration_s: float | None) -> tuple[float, float | None] | None:
    """Ruling: a = max(a, 0.0); b = min(b, duration_s) when both are known. None when b <= a,
    so the run emits nothing and does not count toward the cap."""

def gap_warning(kind: Literal["video", "audio"], index: int, run: tuple[float, float | None], sent: int) -> AssetWarning | None:
    """PARTIAL_DECODE "<kind> stream <index>: undecodable <a:.2f>-<b:.2f> s" for a clamped run
    (b may be "end"). None once `sent` reaches MAX_GAP_WARNINGS."""

def gap_summary(total_runs: int) -> AssetWarning | None:
    """PARTIAL_DECODE "<total_runs - MAX_GAP_WARNINGS> more undecodable runs not listed", or None
    when total_runs <= MAX_GAP_WARNINGS."""
```

`PyAVDecoder` matches the `Decoder` Protocol character for character, and a pyright-checked test assigns it to a `Decoder` variable.

### How `PyAVDecoder` uses them
Implementation notes, each naming the rule it implements.

- **Opening (R9, R10, ruling 4).** Both methods are generators. On the first `next()`:
  1. R9's argument checks raise `ValueError`. `chunk_n = half_up(chunk_s * sample_rate)` must be at least 1, and `track` must satisfy `0 <= track < len(asset.audio)`.
  2. **Ruling 4:** if there's nothing to decode, return without opening the file. That means `iter_frames` with `asset.video is None`, or `iter_audio` with `track is None` and `asset.audio == ()`.
  3. `av.open(str(asset.path))` inside `with`. Any `av.FFmpegError` or `OSError` from it becomes `DecodeError(UNREADABLE, "cannot open: <message>")`.
  4. The stream is `container.streams[i]`, where `i` is `asset.video.index`, or for audio the `.index` of `asset.audio[track]` (or of `asset.default_audio` when `track` is None). E2 never re-selects (R4).
  5. If `i` is out of range, or the stream's `type` isn't the expected kind, raise `DecodeError(UNREADABLE, "<kind> stream <i>: not in container")`.
  6. If `cast("CodecContext | None", stream.codec_context) is None`, raise `DecodeError(UNSUPPORTED_CODEC, "<kind> stream <i>: no decoder for codec '<asset codec>'")`.

  E2 never reads `asset.warnings`.
- **Video loop (R1, R5-R7, R10).** For each packet of `container.demux(stream)`:
  - `packet.decode()`.
  - For each frame with a `pts`: `t = clock_s(...)`.
  - If `frame_kept(...)` and (`every_s is None` or `window_index(t, every_s)` is greater than the last yielded window), the frame is converted, R6 literally:
    1. `arr = frame.to_ndarray(format="rgb24")` at stored size;
    2. `arr = np.rot90(arr, asset.video.rotation // 90)`;
    3. if `upright_size(*arr.shape[:2]) != arr.shape[:2]`, then `arr = VideoFrame.from_ndarray(np.ascontiguousarray(arr), format="rgb24").reformat(width=W2, height=H2, interpolation=Interpolation.AREA).to_ndarray()`. `AREA` is E2's T1 filter under R6.
    4. `pixels = np.ascontiguousarray(arr)`, then `.copy()` if `pixels.base is not None`, so pixels always own their memory.
  - Rotation comes only from `asset.video.rotation`, never from `VideoFrame.rotation` or side data.
- **Audio loop (R1, R8, R10).** For each packet:
  - `packet.decode()`.
  - Each decoded frame goes through `av.AudioResampler(format="flt", layout="mono", rate=sample_rate).resample(frame)`. Mono output means multichannel input is downmixed by FFmpeg. The resampler is flushed with `resample(None)` at end of stream.
  - For each resampled frame `rf` of `n` samples:
    1. `t = clock_s(rf.pts, rf.time_base, container_start_s)`, or None if `rf.pts` is None.
    2. `p = place_audio(t, n, run_end_s=..., ...)`, where `run_end_s = run_start_s + run_n / sample_rate` comes from an integer sample count, so it never drifts. It is None before the first run.
    3. The piece `(p.new_run, p.start_s, concat(zeros(p.fill), samples[p.skip : p.skip + p.keep]))` goes into `chunk_runs`.
  - `chunk_runs` allocates a fresh buffer per chunk, so every yielded chunk owns its array. It clips in place to [-1.0, 1.0], because AAC can overshoot and M0 documents that range (T1).
- **`place_audio` (R1, R8, ruling 7)**, with `period = 1 / sample_rate`:
  - **No PTS.** If `t_s` is None and a run exists, the frame continues the run at `run_end_s`. With no previous end, it is neutral: `keep = 0`, so it is discarded, with no warning.
  - **The gap.** `gap = t_s - run_end_s`. A new run starts when `run_end_s` is None or `gap > AUDIO_GAP_FILL_S`.
  - **Within a run (ruling 8):**
    - `period < gap <= AUDIO_GAP_FILL_S`: `fill = half_up(gap * sample_rate)`. Exactly `AUDIO_GAP_FILL_S` is filled.
    - `gap < 0`: `skip = min(n, half_up(-gap * sample_rate))`.
    - `gap` of at most one period: ignored.
  - **R1 step 2.** If the first kept sample's time is below 0, `ceil(-t * sample_rate - 1e-9)` more leading samples are skipped.
  - **R1 step 3.** With `first` the time of the first kept sample, `keep` is capped at `max(0, ceil((duration_s - first) * sample_rate - 1e-9))`. `fill = 0` when `keep == 0`.
  - A chunk's last sample is at `start_s + (n - 1) / sample_rate`.
- **`chunk_runs` (R8, ruling 7).**
  - A `new_run` piece, even an empty one, flushes the pending samples as a (possibly short) chunk and starts a run at its `start_s`.
  - Samples, fill zeros included, fill a `chunk_n` buffer. A full buffer is yielded, and the next chunk starts at `run_start_s + samples_so_far_in_run / sample_rate`.
  - A fill that crosses a chunk boundary is split across the chunks.
  - The remainder is yielded at the end.
  - No chunk is ever empty.
- **Gap runs (R10, rulings 1, 5, 6).**
  - **A good item** is a decoded frame that has a PTS, from a packet whose `decode()` succeeded, counted before R1/R7 drops. Being dropped, including for being non-monotonic, is an R1/R7 drop, not a gap.
    - Video: `start = end = t_s`. A sampled frame is good only once its conversion succeeds. If conversion fails, it is failed only.
    - Audio: `start = t`, `end = t + n_samples / source_rate`, both from the decoded (pre-resample) frame. A frame whose `resample()` raises is failed only, never also good.
    - A packet that decodes cleanly but returns no frame changes nothing.
  - **A failed item** is any `av.FFmpegError` (every PyAV error subclasses it) raised by `packet.decode()`, `resample()`, `to_ndarray()`, `reformat()` or `from_ndarray()`, or by the demux iterator.
    - After a demux error, demuxing stops, and the run stays open to EOF.
    - After any other failure, demuxing continues.
    - The decoder is not drained after a demux error (T1).
  - **Neutral:**
    - A decoded frame with `pts` None neither opens nor closes a run.
    - The end-of-stream flush (the empty packet) is never a failure. Its errors are logged at debug level.
  - **Reporting:**
    - Every run, closed or EOF, passes through `clamp_run` and then `gap_warning`, and a non-None result goes to `warn`. Only runs that survive `clamp_run` count toward the cap and toward `gap_summary`.
    - `gap_on_eof` adds at most one run: the open run, or the early-EOF run, never both.
    - `gap_summary` is called only after the loop finishes normally (not in `finally`), so an early close skips it.
    - `warn` is never wrapped.
    - No `av` exception escapes after the first item.
- **Buffering (R10).** At most one packet's decoded frames, one converted frame and one pending audio chunk at a time.
- **Logging.** `logging.getLogger(__name__)` at debug level, with `extra={"asset_id": asset.id, "stage": "decode"}`.

## Acceptance
**Hand-built assets.**
- Every `AssetInfo` is built by hand from M0's types, because E1 is being built in parallel. Values are as in the table below.
- Every one has `id = "tsid1:" + "0" * 64` and `warnings = ()`. Decoders never read warnings, so no probe details are copied in.
- `path = FIXTURES / <name>` unless the row says otherwise.
- Values come from ffprobe on the committed fixtures (FFmpeg 7.1.1), and from M0's fixture spec for rotated_270.mp4.

| Asset | `duration_s` | `video` = `VideoInfo(index, codec, w, h, fps_avg, vfr, rotation)` | `audio` |
| --- | --- | --- | --- |
| clean.mp4 | 5.0 | `(0, "h264", 320, 240, 25.0, False, 0)` | `(AudioStreamInfo(1, "aac", "und", True),)` |
| vfr.mp4 | 5.933333 | `(0, "h264", 320, 240, 1500 / 89, True, 0)` | `()` |
| start_offset.mp4 | 5.52 (video end: 1.52 + 4.0) | `(0, "h264", 320, 240, 25.0, False, 0)` | `(AudioStreamInfo(1, "aac", "und", True),)` |
| multi_audio.mkv | 3.064 (container duration) | `(0, "h264", 320, 240, 25.0, False, 0)` | `(AudioStreamInfo(1, "aac", "eng", True), AudioStreamInfo(2, "aac", "eng", False))`. Stream 1 is 440 Hz, stream 2 is 660 Hz (make_fixtures.py). |
| rotated.mp4 | 5.0 | `(0, "h264", 320, 240, 25.0, False, 90)` | `(AudioStreamInfo(1, "aac", "und", True),)` |
| rotated_270.mp4 | 1.0 | `(0, "h264", 320, 240, 5.0, False, 270)` | `()` |
| uhd_4k.mp4 | 1.0 | `(0, "h264", 3840, 2160, 5.0, False, 0)` | `()` |
| hdr10.mkv | 2.0 | `(0, "hevc", 320, 240, 25.0, False, 0)` | `()` |
| truncated.mp4 | 6.0 | `(0, "h264", 320, 240, 25.0, False, 0)` | `(AudioStreamInfo(1, "aac", "und", True),)` |
| av_mismatch.mp4 | 3.0 (video end) | `(0, "h264", 320, 240, 25.0, False, 0)` | `(AudioStreamInfo(1, "aac", "und", True),)` |
| no_audio.mp4 | 3.0 | `(0, "h264", 320, 240, 25.0, False, 0)` | `()` |
| prores.mov | 1.0 | `(0, "prores", 160, 120, 10.0, False, 0)` | `()` |
| unknown_codec.mov | 1.0 | `(0, "unknown", None, None, 25.0, False, 0)` | `()` |
| not_media.txt | None | `(0, "unknown", None, None, None, False, 0)` | `()` |
| long_3h.mp4 | 10800.0 | `(0, "h264", 64, 36, 1.0, False, 0)` | `()` |
| réunion 01.mp4 | 2.0 | `(0, "h264", 240, 160, 25.0, False, 0)` | `(AudioStreamInfo(1, "aac", "und", True),)` |
| gone.mp4 (`tmp_path / "gone.mp4"`, a copy of clean.mp4 deleted after the asset is built) | 5.0 | as clean.mp4 | as clean.mp4 |
| bad_index (path clean.mp4) | 5.0 | `(5, "h264", 320, 240, 25.0, False, 0)` | `(AudioStreamInfo(7, "aac", "und", True),)` |
| missing_video (`tmp_path / "absent.mp4"`, never created) | None | `None` | `()` |
| stereo.wav (`tmp_path / "stereo.wav"`, written in the test with stdlib `wave` + numpy: 1.0 s, 44 100 Hz, 2 channels, s16, left 440 Hz, right 1000 Hz, amplitude 0.4) | 1.0 | `None` | `(AudioStreamInfo(0, "pcm_s16le", None, True),)` |
| fake_audio (path clean.mp4; `av.open` is patched to return a stand-in container whose stream 1 has `type == "audio"`, `codec_context = None`, `start_time = 0`) | 5.0 | `None` | `(AudioStreamInfo(1, "unknown", None, True),)` |

`D = PyAVDecoder()`, and `sink` is a list whose `.append` is passed as `warn`. `...` stands for `uv run pytest tests/smoke/test_decode.py -q`. Each row's tests share the `-k` prefix.

| # | Rule / case | Command | Expected |
| --- | --- | --- | --- |
| 1 | The hand-built table matches the manifest | `... -k test_assets_` | `1 passed`. Every fixture asset name above, excluding the `tmp_path`, bad_index and fake_audio rows, is in `{e["name"] for e in manifest["fixtures"]}`. |
| 2 | Protocol conformance | `... -k test_protocol_` | `1 passed`. `decoder: Decoder = PyAVDecoder()` type-checks (row 21), and `next(decoder.iter_frames(clean, None, warn=sink.append))` is a `Frame`. |
| 3 | R1, R7: VFR times come from PTS | `... -k test_vfr_` | `3 passed`. (a) `D.iter_frames(vfr, None, ...)` yields 100 frames, each within 1/30 s of the frozen list `[i*0.1 for i in range(20)] + [2+i/30 for i in range(60)] + [4+i*0.1 for i in range(20)]`. index/fps drifts by up to 0.8 s and fails. (b) `every_s=0.5` gives 12 frames at about 0.0, 0.5, ..., 5.5. (c) `every_s=0.05` gives 80 frames, and empty windows yield nothing. |
| 4 | R1: container-clock normalization | `... -k test_start_` | `2 passed`. (a) start_offset.mp4: the first `iter_frames` `t_s` is within 0.04 of 1.52, and the first `iter_audio` chunk has `start_s` in [0.0, 0.002]. (b) multi_audio.mkv (container start -0.064, video start 0.0): the first `t_s == approx(0.064, abs=0.002)`. |
| 5 | R5: rotation with no resize, pixel-exact | `... -k test_rotated_` | `2 passed`. (a) The first rotated.mp4 frame has shape (320, 240, 3) and equals `np.rot90(<first clean.mp4 frame>, 1)`. The video streams are identical, and FFmpeg 7.1.1 autorotate gives this exact array. (b) rotated_270.mp4 gives (320, 240, 3), with `pixels[160, 230]` red (R > 200, B < 60) and `pixels[160, 10]` blue (B > 200, R < 60). That is M0's assigned test. |
| 6 | R6: the resize path | `... -k test_downscale_` | `2 passed`. uhd_4k.mp4 gives 5 frames, each (432, 768, 3) uint8. clean.mp4 stays (240, 320, 3), so nothing is upscaled. |
| 7 | 8-bit from 10-bit PQ | `... -k test_hdr_` | `1 passed`. hdr10.mkv gives 50 frames, each (240, 320, 3) uint8, and `sink == []`. Tone mapping is deferred (row 23). |
| 8 | Pixels own their memory | `... -k test_pixels_` | `1 passed`. The first frame of each of clean.mp4, rotated.mp4 and uhd_4k.mp4 has `pixels.base is None` and `pixels.flags.owndata`, is C-contiguous, and is not writeable. |
| 9 | Unicode path, passed to `av.open` as `str` | `... -k test_unicode_` | `1 passed`. A spy wrapping `av.open` records `isinstance(arg, str)` as True. `réunion 01.mp4` yields 50 frames of (160, 240, 3). |
| 10 | R8 on real audio | `... -k test_audio_` | `4 passed`. (a) `D.iter_audio(clean, 16_000, chunk_s=1.0, ...)`: chunks are float32, 1-D, `sample_rate == 16000`, with values in [-1, 1]; every chunk but the last is exactly 16 000 samples; chunks are back to back (`next.start_s == approx(prev.start_s + n / 16000)`); the total is in [78 976, 80 000]; the FFT peak is 440 ± 2 Hz. (b) The same at `sample_rate=8000`: chunks of 8 000, a total in [38 976, 40 000], peak 440 ± 2 Hz. (c) av_mismatch.mp4: the total is in [46 976, 48 000], and the last sample time `start_s + (n - 1) / 16000` is below 3.0. (d) no_audio.mp4: `list(D.iter_audio(...)) == []` and `sink == []`. |
| 11 | Track selection | `... -k test_tracks_` | `2 passed` (parametrized). On multi_audio.mkv, `track=None` gives an FFT peak at 440 ± 2 Hz (the default stream, 1), and `track=1` gives 660 ± 2 Hz (stream 2). |
| 12 | Downmix and resample from stereo 44.1 kHz | `... -k test_downmix_` | `1 passed`. stereo.wav gives mono float32 chunks at 16 000 Hz, with 15 000 to 16 000 samples in total. The FFT has peaks within ± 2 Hz of both 440 and 1000 Hz, each at least 25% of the largest peak. |
| 13 | R10: damaged media and unreadable files | `... -k test_corrupt_` | `5 passed`. (a) `D.iter_frames(truncated, None, ...)`: at least 75 frames, `t_s` strictly increasing, the last in [3.0, 3.3]. `sink` holds exactly one `PARTIAL_DECODE`, matching `video stream 0: undecodable (\d+\.\d\d)-6\.00 s` with group 1 equal to `f"{last_t_s:.2f}"`. This holds whether PyAV raises at the cut (an open run closed at EOF) or ends cleanly (the early-EOF run). No exception. (b) `D.iter_audio(truncated, ...)`: 1 to 95 999 samples in total, and exactly one `PARTIAL_DECODE`, matching `audio stream 1: undecodable \d+\.\d\d-6\.00 s`. (c) `list(D.iter_frames(truncated, None, warn=raiser))`, where `raiser` raises `RuntimeError("sink")`, raises that same `RuntimeError`. (d) `next(D.iter_frames(not_media, None, ...))` raises `DecodeError` with `.warning.code is UNREADABLE`. (e) gone.mp4: `next(D.iter_frames(gone, None, ...))` and `next(D.iter_audio(gone, ...))` each raise `DecodeError` with `UNREADABLE`, before any item. |
| 14 | R10: a stream without a decoder gives `UNSUPPORTED_CODEC` | `... -k test_codec_` | `3 passed`. (a) `next(D.iter_frames(unknown_codec, None, ...))` raises `DecodeError` with code `UNSUPPORTED_CODEC` and `"video stream 0"` in the detail. PyAV opens this file and sets `codec_context = None` for stream 0 (see Read first), and M0's R10 maps "selected stream has no decoder" to `UNSUPPORTED_CODEC`, so the test accepts only that code. (b) `next(D.iter_audio(fake_audio, ...))`, with `av.open` patched via `monkeypatch`, raises `DecodeError` with `UNSUPPORTED_CODEC` and `"audio stream 1"` in the detail. (c) `D.iter_frames(prores, None, ...)` yields 10 frames of (120, 160, 3) uint8: CPU decode, whatever probe says. |
| 15 | A stream index that isn't in the container | `... -k test_index_` | `1 passed`. bad_index: `next(D.iter_frames(...))` and `next(D.iter_audio(...))` each raise `DecodeError` with `UNREADABLE` (`"video stream 5: not in container"`, `"audio stream 7: not in container"`). |
| 16 | Ruling 4: no stream, no open | `... -k test_nostream_` | `2 passed`. missing_video: `list(D.iter_frames(...)) == []` and `list(D.iter_audio(...)) == []`, with no `DecodeError` even though the file doesn't exist, and `sink == []`. |
| 17 | R9: argument validation | `... -k test_args_` | `8 passed`. On the first `next()`, each raises `ValueError`: `iter_frames(clean, 0)`; `iter_frames(clean, -0.5)`; `iter_audio(clean, 0)`; `iter_audio(clean, chunk_s=0)`; `iter_audio(clean, chunk_s=1e-5)` (`half_up(0.16) == 0`); `iter_audio(clean, track=1)`; `iter_audio(clean, track=-1)`; `iter_audio(no_audio, track=0)`. |
| 18 | Pure timestamp math | `... -k test_math_` | `32 passed`. Breakdown: `half_up` (1: `half_up(0.5) == 1`, `half_up(2.5) == 3`, `half_up(-0.5) == 0`); `clock_s` (1); `frame_kept` (1, property: kept outputs strictly increase and lie in [0, duration)); `window_index` (1: `window_index(0.3, 0.1) == 3`, property: `k*e <= t + 1e-9*e` and `t < (k+1)*e`); `upright_size` (1: (2160, 3840) gives (432, 768), (240, 320) unchanged, property: max side ≤ 768, both ≥ 1); `place_audio` hand cases (10, below); `place_audio` property (1: `skip + keep <= n`, `fill <= half_up(AUDIO_GAP_FILL_S * sr)`, `fill == 0` when `new_run`); `chunk_runs` hand cases (2, below); `chunk_runs` property (1: totals preserved per run, every chunk but a run's last has exactly `chunk_n` samples, starts back to back, no empty chunk); the gap state machine (1, below); the gap property (1: over random good/fail/no-PTS event lists, clamped runs are ordered and disjoint with `a < b`, and EOF adds at most one run); early EOF (5, below); `clamp_run` (5, below); the cap (1, below). |
| 19 | R10: buffering bound | `... -k test_long_` | `2 passed` (both marked `slow`). (a) `tracemalloc`: a full `D.iter_frames(long_3h, None, ...)` pass that keeps no frames yields 10 800 frames, the last within 1 s of 10 799, with a traced peak under 16 MB. Why 16 MB: R10 allows a fixed number of frames; 10 largest frames (768x432x3, about 1 MB each) is about 10 MB, plus headroom. numpy reports its buffers to tracemalloc, so keeping long_3h's 10 800 frames (about 75 MB) fails. (b) Peak RSS (covers FFmpeg's C heap), measured in a fresh interpreter: `subprocess.run([sys.executable, "-c", SCRIPT, str(FIXTURES)], capture_output=True, text=True, timeout=120, check=True)`. In SCRIPT, `peak()` is `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`, times 1024 on Linux (KiB) and as-is on macOS (bytes). SCRIPT imports av and decodes one clean.mp4 frame, then takes `baseline = peak()`, consumes long_3h, and prints exactly one line: `baseline=<int bytes> peak=<int bytes>`. The test parses that line with `re.fullmatch(r"baseline=(\d+) peak=(\d+)", out.strip())` and asserts `peak <= baseline + 100 * 2**20`. The builder records both numbers in the PR under Numbers. |
| 20 | Source of row 3's frozen list (local only, needs ffprobe) | command A1 below | the exact output under A1 |
| 21 | The whole file, plus the gate | `uv run pytest tests/smoke/test_decode.py -q`, then `uv run pyright`, then `make check` | `74 passed`; pyright prints `0 errors, 0 warnings, 0 informations`; `make check` exits 0 |
| 22 | `make smoke` covers it | `make smoke` | The summary line includes at least `74 passed` (other smoke files may add more) and no `failed` or `error` |
| 23 | Deferred: deinterlace (`INTERLACED`) and PQ/HLG tone mapping (`HDR_CONVERTED`) | none | Not in E2. interlaced.mp4 frames come out combed, and hdr10.mkv is 8-bit but not tone-mapped. Reasons: neither is in issue #6's goal or done-when. Deinterlacing needs a `bwdif` filter graph (the only one in E2) plus a comb-artifact metric to test it. Tone mapping needs `zscale` (zimg) or `libplacebo`, which the pyav-ffmpeg wheel build doesn't enable, so it would be a numpy PQ→SDR curve. Follow-up issue for the lead to file: "Media: deinterlace (bwdif) and HDR tone mapping at decode", with tests on interlaced.mp4 and hdr10.mkv. Probe already emits both codes (M0's emitter table). |


**Test count, stated once:** rows 1-19 = 1 + 1 + 3 + 2 + 2 + 2 + 1 + 1 + 1 + 4 + 2 + 1 + 5 + 3 + 1 + 2 + 8 + 32 + 2 = **74**.

Command A1 (row 20):
```bash
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 tests/fixtures/vfr.mp4 | sort -g | awk 'NR==1||NR==20||NR==21||NR==80||NR==81||NR==100{printf "%s ",$0} END{print "lines:",NR}'
```
Expected output, exactly:
```text
0.000000 1.900000 2.000000 3.966667 4.000000 5.900000 lines: 100
```

**Hand-made cases in row 18.** All use `sample_rate=16_000`, `period = 1/16000` and `n = 1024` unless stated. All times are exact in binary.

| `place_audio` case | Input | Expected `Placement` |
| --- | --- | --- |
| first frame | `t=0.0, run_end=None, dur=5.0` | `new_run=True, start_s=0.0, fill=0, skip=0, keep=1024` |
| contiguous | `t=0.25, run_end=0.25` | `new_run=False, fill=0, skip=0, keep=1024` |
| sub-period gap ignored | `t=0.25 + 0.5/16000, run_end=0.25` | `fill=0, skip=0` |
| gap filled | `t=0.375, run_end=0.25` | `fill=2000` (`half_up(0.125 * 16000)`) |
| gap of exactly 0.5 s filled | `t=0.75, run_end=0.25` | `new_run=False, fill=8000` |
| gap over 0.5 s: new run | `t=0.8, run_end=0.25` | `new_run=True, start_s=0.8, fill=0` |
| overlap dropped | `t=0.24, run_end=0.25` | `skip=160, keep=864` |
| pts None continues the run | `t=None, run_end=0.25` | `new_run=False, fill=0, skip=0, keep=1024` |
| pts None with no run: neutral | `t=None, run_end=None` | `keep=0, fill=0` |
| negative start trimmed | `t=-0.01, run_end=None` | `new_run=True, skip=160, start_s=approx(0.0), keep=864` |

`chunk_runs` cases, with `chunk_n=1000` at 16 kHz:
1. **Fill crosses a boundary.** Pieces `(True, 0.0, 900 ones)`, then `(False, _, 300 zeros + 100 ones)`, then `(True, 2.0, 50 ones)` give chunks of 1000 (900 ones, 100 zeros) at 0.0, 300 (200 zeros, 100 ones) at 0.0625, and 50 at 2.0.
2. **Empty new run.** Pieces `(True, 0.0, 100 ones)`, `(True, 2.0, empty)`, `(False, _, 50 ones)` give chunks of 100 at 0.0 and 50 at 2.0.

**Gap state machine.** The events good(0.0), good(0.04), fail, fail, no-pts frame, good(0.2), fail, EOF with `duration_s=1.0` give the runs `(0.04, 0.2)` and `(0.2, 1.0)`. The no-pts frame neither opens nor closes a run. With `duration_s=None`, the last run is `(0.2, None)` and its detail ends `-end s`.

**Early EOF** (`gap_on_eof`, 5 parametrized cases):

| State | `duration_s` | Expected |
| --- | --- | --- |
| no open run, `last_good_end_s=3.24` | 6.0 | `(3.24, 6.0)`, detail `video stream 0: undecodable 3.24-6.00 s` |
| no open run, `last_good_end_s=5.5` | 6.0 | `None` (within `EARLY_EOF_S`) |
| no open run, `last_good_end_s=5.0` | 6.0 | `None` (exactly `EARLY_EOF_S` is not "more than") |
| no open run, `last_good_end_s=3.24` | None | `None` |
| earlier closed run, then a clean early EOF: events good(0.0), fail, good(1.0), good(3.24), EOF | 6.0 | runs `(0.0, 1.0)` then `(3.24, 6.0)`: the EOF adds one more `PARTIAL_DECODE` |

**`clamp_run`** (5 parametrized cases): `((-0.5, 1.0), 6.0)` gives `(0.0, 1.0)`; `((1.0, 7.0), 6.0)` gives `(1.0, 6.0)`; `((2.0, 1.5), 6.0)` gives None; `((6.0, 6.0), 6.0)` gives None; `((1.0, None), None)` gives `(1.0, None)`.

**Cap.** 25 runs give 20 non-None `gap_warning`s (the first is `video stream 0: undecodable 0.00-1.00 s`), the 21st returns None, and `gap_summary(25)` has detail `5 more undecodable runs not listed`; `gap_summary(20) is None`. If the 25th run is an early-EOF run, it counts the same way. A run that `clamp_run` rejects counts toward neither.

## Out of scope
- Deinterlacing and tone mapping (row 23).
- **The probe-then-decode integration test.** It's a lead follow-up once both E1 and E2 are on main: a new file, `tests/smoke/test_probe_decode.py`, checking that `probe()` then `iter_frames` on rotated.mp4, rotated_270.mp4, vfr.mp4 and start_offset.mp4 matches the hand-built results. That way neither spec edits the other's tests.
- `CROPPED` and shot-based sampling (C3). VAD, ASR and chunk seams (E3).
- Seeking for faster sampling. Every frame is decoded; only sampled frames are converted.
- Decoder threading, NVDEC/torchcodec, pixel aspect ratio (anamorphic SD comes out with square pixels).
- New committed fixtures. Stereo and 44.1 kHz audio is covered by the WAV written in the test; mid-file corruption is covered by the pure tests.
- Any code other than `PARTIAL_DECODE` (via `warn`) and `UNREADABLE`/`UNSUPPORTED_CODEC` (via `DecodeError`), per M0's emitter table.

## Risks
- **truncated.mp4 must give exactly one warning either way.** If PyAV raises at the cut, one run stays open to EOF. If it ends cleanly, the early-EOF run fires. If row 13 shows two runs (a good frame between a failed packet and the demux error), that is real behavior, not a test to loosen: stop and report the event sequence PyAV produced.
- **Resampler PTS.** If resampled frames have `pts is None` or are shifted by filter delay, R8's gap math sees false gaps or overlaps. Rows 10(a) and 12 catch this. The fallback is the decoded frame's PTS plus a running sample count, a T1 change inside the audio loop.
- **Resize cost.** R6 applied literally converts a sampled 4K frame at full size before resizing: a 25 MB intermediate, freed at once. That's acceptable at v0.1 sampling rates. If C1 profiling flags it, the upgrade is one `to_ndarray(width=, height=)` call when the rotation is 0, which is identical in that case.
- **pyright strict.** Use `cast("NDArray[np.uint8]", ...)` on `to_ndarray` and `cast("CodecContext | None", ...)` on `codec_context`. No `# type: ignore`. The stand-in container in row 14(b) lives in tests, which pyright checks in standard mode.
- **pytest `filterwarnings = error`.** A DeprecationWarning from PyAV, numpy or hypothesis fails the suite. Fix the call; don't silence it without a card.
- **FFmpeg 8.1 vs. the 7.1.1 values.** The hand-built assets pin the metadata, so decode tests don't depend on probe. The lead's integration test is where the two meet.
- **ru_maxrss units differ by OS.** The normalization in row 19(b) is what makes one 100 MB bound valid on both CI platforms.

## Decision cards

### Decision (T2): truncated.mp4 decodes to a clean EOF with no failing packet
Context: Before the amendment, M0's R10 opened a gap run only when packets or frames failed to demux or decode. If PyAV stops at the cut with no error, the frames before the cut still come out, but no `PARTIAL_DECODE` is sent, which breaks "keep partial results, record the gap". R10 is M0's.
Options:
- A. Amend R10: at EOF, if the last good item ends more than 1.0 s before `duration_s`, record a gap run from that end to `duration_s`. Pros: catches truncation however FFmpeg reports it. Cons: false positives when metadata overstates the duration, and a new 1.0 s constant.
- B. Leave R10 alone and drop the truncated warning assertion. Cons: weakens a test, and silent truncation is what the table forbids.
- C. Detect truncation in probe (E1), when the byte size is shorter than the last sample offset. Cons: MP4-specific, and it misses MKV.
Hardest to reverse: A, because it changes when users see `PARTIAL_DECODE`.
**Decided 2026-10-17 (owner); implemented via M0 R10 amendment.** A, with `EARLY_EOF_S = 1.0` owned by M0. The early-EOF run fires whenever the stream's last decode step was clean, meaning no gap run is open at EOF, and decoding ended more than `EARLY_EOF_S` before `duration_s`. Earlier closed runs don't affect it. It produces one `PARTIAL_DECODE` and counts toward the cap. E2 owns the implementation (`gap_on_eof`) and the tests (row 13(a)/(b), plus the early-EOF cases in row 18).
Revisit if: real files with overstated metadata durations produce false `PARTIAL_DECODE`s.
