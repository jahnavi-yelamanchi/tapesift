# 21. One safe opener for every media stage, with a demuxer allow-list

Issue: #21   Lane: Media   Status: approved 2026-10-19 (owner, gate 1; all 7 cards take the recommended option)
Revisions: 2026-10-19 r2, after spec-critic. The open now goes through a file descriptor (card 6). Card 2 gets a table of refused real-world formats, each with a test. mov drefs and the other allowed demuxers are checked for opening other files. Filename tests are added. The `UnsafeInputError` card is added. Acceptance numbers are pinned.

## Decision cards

These are at the top because the build can't start until they're answered. Each card says which option the rest of this spec assumes (the recommendation). Every FFmpeg behaviour cited was observed by the planner on 2026-10-19, with PyAV 19.0.1 and libavformat 63.1.102, in scratch directories outside the repo (see Read first).

### Decision needed (T2): which warning code a refused input carries
**Context.** The opener refuses two new kinds of input:
- files that aren't regular files: FIFO, device, directory, socket;
- containers whose demuxer isn't on the allow-list.

Probe raises `ProbeError` and decode raises `DecodeError`; each carries one code. M0 defines `UNREADABLE` as "not media, or cannot be opened at all". The messy-data row is "Not a media file or unopenable ... Skip with the exact reason", and the detail string is where that reason goes.

FFmpeg rejects a demuxer that isn't on the whitelist with `av.error.ArgumentError` (EINVAL, "Invalid argument"), which doesn't say why. PyAV only attaches FFmpeg's "Format not on whitelist" log line when PyAV logging is switched on for the whole process. The opener therefore maps an `ArgumentError` from `av.open` to its own message. A demuxer could also return EINVAL from a header it rejects, and we can't tell the two apart, so the message names both causes.

**Options.**
- **A. Reuse `UNREADABLE`, with exact details** (assumed below). The details are `not a regular file: <kind>` and `container format not allowed or header invalid`. Probe prefixes them with `UnsafeInputError: ` and decode with `cannot open: `. Files that FFmpeg can't identify at all (for example an `.m3u8` or `.nfo` once card 6 hides the extension) keep FFmpeg's `InvalidDataError` detail, as `not_media.txt` does today. Pros: no change to the enum, the schema, the spec table or the manifest, and the row already covers "unopenable". Cons: one code covers both "broken" and "refused by policy".
- **B. A new code, `REFUSED_INPUT`.** Pros: precise, and a user can filter on it. Cons: changes M0's `WarningCode`, the spec.md table, the output schema, `test_code_coverage` and the fixtures. That makes it a T3 schema change.
- **C. Like A, but turn on PyAV logging and capture FFmpeg's line, so the detail names the demuxer.** Pros: the most exact reason. Cons: `av.logging.set_level` applies to the whole process and reroutes every stage's FFmpeg errors.

**Hardest to reverse.** B, because it's a schema change.
**Recommendation.** A.
**Would change my mind.** The runner's report needs to tell policy refusals apart from broken files. Then B, at the next schema bump.
**Blocked until answered.** The build.

### Decision needed (T2): which container formats are allowed
**Context.** On main, every format FFmpeg can detect opens. An allow-list makes some real files that used to open come back `UNREADABLE`. The issue lists nine demuxers, and the committed fixtures need only `mov` and `matroska`.

The table lists every family of real-world media the critic named. Each one, except DTS, was muxed in a scratch directory and opened two ways:
- "Main": `av.open("file:"+path, options={"protocol_whitelist": "file"})`;
- "A" and "B": through this spec's opener (card 6), with that option's list.

| Family (example files) | FFmpeg demuxer | Opens on main | Under A (the nine) | Under B (A + `mpeg` + `aiff`) | Test case |
| --- | --- | --- | --- | --- | --- |
| Raw H.264 (`.h264`, `.264`) | `h264` | yes | refused: `ArgumentError` | refused | `h264` |
| Raw HEVC (`.hevc`, `.265`) | `hevc` | yes | refused: `InvalidDataError` (remuxed from hdr10.mkv; FFmpeg's content probe is too weak without the extension) | refused | `hevc` |
| Raw MPEG-4 Part 2 (`.m4v` elementary stream) | `m4v` | yes | refused: `ArgumentError` | refused | `m4v` |
| AC-3 (`.ac3`) | `ac3` | yes | refused: `ArgumentError` | refused | `ac3` |
| E-AC-3 (`.eac3`, `.ec3`) | `eac3` | yes | refused: `ArgumentError` | refused | `eac3` |
| DTS (`.dts`) | `dts` | not checked | refused by construction (not on the list) | refused | none: the wheel has no DTS encoder, and a hand-made frame isn't worth it |
| MPEG program stream (`.mpg`, `.mpeg`, `.vob`, camcorder `.mod`/`.tod`) | `mpeg` | yes (`.mpg` with mp2 audio, `.mpg` with mpeg1video, `.vob` with ac3) | refused: `ArgumentError` | **allowed** | `mpeg` |
| AIFF (`.aif`, `.aiff`) | `aiff` | yes | refused: `ArgumentError` | **allowed** | `aiff` |
| Flash video (`.flv`) | `flv` | yes | refused: `ArgumentError` | refused | `flv` |
| ASF (`.wmv`, `.wma`, `.asf`) | `asf` | yes (`.wma` with wmav2, `.wmv` with mpeg4) | refused: `ArgumentError` | refused | `asf` |
| AMR (`.amr`) | `amr` | yes (written by hand: `#!AMR\n` plus 50 frames of 32 bytes each starting `0x3C`) | refused: `ArgumentError` | refused | `amr` |
| Core Audio (`.caf`) | `caf` | yes | refused: `ArgumentError` | refused | `caf` |
| Sony Wave64 (`.w64`) | `w64` | yes | refused: `ArgumentError` | refused | `w64` |

The 12 testable rows are pinned by `test_refused_family`. Each case asserts three things:
- main's options open the file as that demuxer;
- `open_media` raises the error in the table;
- `probe` raises `UNREADABLE`.

**Options.**
- **A. The issue's nine** (assumed below): `mov` (mp4, m4a, mov, 3gp), `matroska` (mkv, webm, mka), `avi`, `mpegts`, `wav`, `mp3` (also reads mp2), `aac` (ADTS), `flac`, `ogg` (ogg, oga, opus). Pros: the owner's own list; each is tested. Cons: every family in the table is `UNREADABLE`.
- **B. A plus `mpeg` and `aiff`.** Pros: covers DVD and camcorder footage and Mac audio. Neither demuxer has any call that opens another file (the FFmpeg source check in card 6 covers only the nine, so the builder repeats the grep for these two). Cons: two more allow-list round-trip tests, and the `mpeg` and `aiff` family cases flip to "opens".
- **C. Ban the dangerous demuxers instead** (`concat`, `hls`, `image2`, `*_pipe`, `tty`, `sdp`, ...). Pros: nothing that opens today breaks. Cons: any demuxer added in a future FFmpeg is allowed by default, and FFmpeg has more than 300.

**Hardest to reverse.** C: once users depend on exotic formats opening, taking them away breaks them.
**Recommendation.** A. Adding a format later is one string, plus moving its family test into `test_allowed_format_opens` (T1 then).
**Would change my mind.** The owner's library has `.mpg`, `.vob` or `.aiff` files. Then B.
**Blocked until answered.** The build. Counts below assume A. B keeps the total at 64: `test_allowed_format_opens` grows from 9 to 11, and `test_refused_family` shrinks from 12 to 10.

### Decision needed (T2): does the open timeout bound local reads? (the card the issue asks for)
**Context.** Probe passes `timeout=PROBE_TIMEOUT_S` (30 s, owner 2026-10-17); decode passes no timeout. PyAV turns `timeout` into FFmpeg's interrupt callback: one deadline for open plus header, and the full timeout again for each demux call (from `av.open`'s docstring in PyAV 19). FFmpeg checks the callback only between I/O calls. So it bounds a slow source whose reads keep returning, but it can't break a `read()` or `open()` stuck in the kernel. Observed: `av.open` on a FIFO with `timeout=1.0` was still blocked after `join(4)`. Default-mode `asset_id` reads at most the size plus the first and last 8 MiB (ADR 0012), with plain Python I/O and no bound of its own.

**Options.**
- **A. One constant, `OPEN_TIMEOUT_S = 30.0`, applied by the opener to every stage, plus refusing anything that isn't a regular file without ever blocking** (cards 4 and 6; assumed below). Decode gains the per-demux timeout. A syscall stuck inside the kernel, such as a hung NAS, stays unbounded until a Core-lane follow-up exists: the runner kills a worker that runs past a deadline. Pros: small, and it closes the FIFO hang, the only hang that crafted input can cause. Cons: a dead NAS still stalls one worker until the runner exists.
- **B. A thread with `join(timeout)` inside the opener.** Cons: it can't cancel the C call, so the stuck thread leaks and holds the fd. Reads during `asset_id` and decode stay unbounded.
- **C. Probe in a subprocess with `timeout=`.** Cons: a process spawn per file; decode needs the same; it duplicates the runner's job.

**Hardest to reverse.** C: the process model would leak into every stage.
**Recommendation.** A. The lead files the follow-up issue "Core: per-file wall-clock limit in the runner (kills a stuck worker)".
**Would change my mind.** A stalled NAS shows up in real use before the runner lands.
**Blocked until answered.** The build.

### Decision needed (T2): symlinks (a security choice)
**Context.** Media libraries often use symlinks: git-annex stores every file as one, and Plex and Jellyfin setups link folders together. A symlink can also point at a FIFO, a device, or a file outside the folder the user named.

**Options.**
- **A. Follow symlinks; check and read whatever the link resolves to** (assumed below). `os.stat` and `os.open` both follow links, and the target must be a regular file. Pros: libraries keep working; a link to a FIFO or device is refused; tapesift only reads what the user running it can read. Cons: a link can reach a file outside the named folder.
- **B. Refuse links.** `O_NOFOLLOW` refuses a link in the last path component; links in parent directories still resolve. Pros: stricter. Cons: git-annex and linked libraries come back `UNREADABLE`.
- **C. Follow only links that stay inside the input root.** Cons: probe and decode take one path and know no root; only the runner (Core lane, not built yet) does.

**Hardest to reverse.** B: it trains users to copy their media.
**Recommendation.** A. Revisit C when `tapesift serve` accepts paths from remote clients.
**Would change my mind.** A multi-user or server mode.
**Blocked until answered.** The build.

### Decision needed (T2): edit two existing probe tests and retire `PROBE_TIMEOUT_S`
**Context.** AGENTS.md requires a card before rewriting an existing test. Two tests in `tests/unit/test_probe.py` pin the old open call:
- `test_open_uses_file_url_and_whitelist` asserts `files == ["file:" + resolved]` and `options == [{"protocol_whitelist": "file"}]`;
- `test_timeout_passed` imports `PROBE_TIMEOUT_S`.

The issue asks for a single place for the open rules; a second timeout constant in probe would be a second place.

**Options.**
- **A. Rewrite both, and remove `PROBE_TIMEOUT_S`** (assumed below).
  - The first test is renamed `test_open_uses_fd_and_allow_list`. It asserts `files == ["fd:"]`. It also asserts that the recorded options dict, once its `"fd"` value is popped and checked with `.isdigit()`, equals `{"protocol_whitelist": "fd", "format_whitelist": "mov,matroska,avi,mpegts,wav,mp3,aac,flac,ogg"}`, written as a literal.
  - The second test imports `OPEN_TIMEOUT_S` from `tapesift.media.safe_open` and asserts that it equals 30.0.
  - The test-function count is unchanged (`scripts/ci/test_guard.py`). Both get stricter.
- **B. Keep `PROBE_TIMEOUT_S` in probe.py as an alias.** Cons: a second name for one value. The first test still has to change.
- **C. Keep the old name `test_open_uses_file_url_and_whitelist`.** Cons: the name would describe something the code no longer does.

**Hardest to reverse.** None of the three; all are cheap.
**Recommendation.** A.
**Would change my mind.** Nothing likely.
**Blocked until answered.** The build.

### Decision needed (T2): open through a checked file descriptor (`fd:`), not a `file:` URL
**Context.** The first draft did `stat` on the path and then `av.open("file:" + path)`. That leaves two gaps:
- the path can be swapped for a FIFO between the check and the open, and the open then blocks forever;
- the `file` protocol stays allowed, so any demuxer that opens a second file by name can still read local files.

An alternative opens the file once in Python, checks that descriptor, and hands it to FFmpeg's `fd` protocol. Observed with PyAV 19.0.1 on macOS:
- **Opening works.** `os.open(path, O_RDONLY | O_NONBLOCK)`, then `os.fstat`, then `av.open("fd:", options={"protocol_whitelist": "fd", "fd": "<n>", ...})` opened all 24 media fixtures with their usual demuxer.
- **FFmpeg keeps its own copy of the fd.** It `dup`s the descriptor (`fd_open` in `libavformat/file.c`). Closing ours right after `av.open` left all 207 packets of clean.mp4 demuxable, and seeking worked.
- **FIFOs don't block.** `O_NONBLOCK` opens a FIFO for reading at once, and `fstat` then says it is a FIFO.
- **A swap after the open changes nothing.** The descriptor was opened, the path unlinked and replaced with a FIFO, and the file still opened as the original mp4.
- **Nested file opens become impossible.** With `protocol_whitelist="fd"`, an ffconcat list opened *without* `format_whitelist` still could not read its neighbour (`ArgumentError`). A mov alias dref, with `enable_drefs=1` forced on, read 0 neighbour packets; the same file over `file:` read 125.
- **The filename never reaches FFmpeg.** That removes every problem with parsing `file:` URLs: `#`, `%`, `?`, `file:` and `concat:` in names, and Unicode.

The behaviour change: FFmpeg only sees `fd:`, so format detection that relies on the file extension is gone. Observed:
- every fixture and all nine allowed formats are still detected from content;
- a local `.m3u8` and a `.nfo` become `InvalidDataError` instead of opening as `hls` and `tty`;
- a raw `.hevc` remuxed from hdr10.mkv becomes `InvalidDataError` (it isn't on the list anyway).

One more case: FFmpeg's `fd` protocol reads fd 0 (stdin) when no `fd` option is given. Only a nested `fd:` open could hit that. The only nested opens in the nine allowed demuxers are mov drefs, which are off by default, and mov refuses dref paths containing `:` (`mov_open_dref`).

**Options.**
- **A. The fd-based open** (assumed below): `stat` first (so a device is never opened), then `os.open` with `O_NONBLOCK`, then `fstat` the descriptor, `set_blocking(True)`, and `av.open("fd:")` with `protocol_whitelist="fd"`. Pros: no stat/open race on the media read; no nested file opens possible; no URL parsing of names. Cons: extension-only detection is gone; it was verified on macOS only (Linux is proven by the ubuntu CI job, see Risks).
- **B. Keep the `file:` URL** with the stat check. Pros: FFmpeg still sees the extension. Cons: the race stays, and nested reads of local files are blocked only by `format_whitelist` and mov's default.
- **C. Hand PyAV a Python file object.** Cons: every read goes through Python callbacks, which is slow on 3-hour files, and nested opens would still use FFmpeg's own protocols.

**Hardest to reverse.** None; the change is local to one function.
**Recommendation.** A.
**Would change my mind.** A real file type that tapesift must support turns out to be detectable only by its extension.
**Blocked until answered.** The build.

### Decision needed (T2): a new exception type, `UnsafeInputError(OSError)`
**Context.** The opener needs to raise something for "refused". Its class name ends up in user-visible details, because probe's format is `f"{type(e).__name__}: {e.strerror or e}"`. Every current and future stage needs to turn it into `UNREADABLE` without fail.

**Options.**
- **A. A public `UnsafeInputError(OSError)` in `tapesift.media.safe_open`, not re-exported from `tapesift.media`** (assumed below). Pros: probe's and decode's existing `except (FFmpegError, OSError)` clauses catch it unchanged, and any future stage that catches `OSError` around file I/O is safe by default. Tests can assert its type, and the name reads well in a detail. Cons: it is a subclass of `OSError` with no errno.
- **B. Raise a plain `OSError("not a regular file: fifo")`.** Pros: no new type. Cons: the detail becomes `OSError: ...`; tests can't tell a refusal from a real I/O error.
- **C. A `StageError` subclass.** Cons: a `StageError` carries a code and belongs to one stage, while the opener serves every stage. The runner would also see a stage-agnostic error.

**Hardest to reverse.** A or C, once outside code catches the type by name. Today only probe and decode would.
**Recommendation.** A.
**Would change my mind.** The owner wants details to show no Python type names. That would be a separate change to probe's detail format.
**Blocked until answered.** The build.

## Goal
After this lands, every stage opens media through one function, `tapesift.media.safe_open.open_media(path)`. It does four things:
- It refuses anything that isn't a regular file, without blocking.
- It reads the file through a descriptor that it checked itself.
- It lets FFmpeg use only that descriptor (`fd` protocol) and the nine allowed demuxers. FFmpeg enforces the demuxer list after detecting the format and before reading the header.
- It applies one timeout.

So no crafted file can make FFmpeg read a second file. Probe and decode both use it, and `av.open(` appears nowhere else in `src/`.

## Read first
- docs/spec.md: Messy multimodal data (the `UNREADABLE` row: "Skip with the exact reason"); Engineering standards (each stage raises its own exception type; review checklist item 3).
- docs/specs/4-media-types.md: `UNREADABLE`, and `ProbeError` and `DecodeError` with their allowed codes.
- docs/specs/5-probe.md: step 1 (Open), card 2 (`PROBE_TIMEOUT_S`), and the security tests.
- docs/specs/6-decode.md: "Opening" steps 3-6 and row 24.
- ADR 0012: default IDs read the size plus the first and last 8 MiB; only `full_hash=True` reads the whole file.
- Code:
  - `src/tapesift/media/probe.py`: `probe`.
  - `src/tapesift/media/decode.py`: `_open`, lines 296-303.
  - `tests/unit/test_probe.py`: `_spy_on_open` and the security block.
  - `tests/smoke/test_decode.py`: `_patch_open`, `test_review_open_*`, `test_unicode_path_passed_as_str`, and the `_FakeContainer` that `av.open` is patched to return.
- **Observed by the planner on 2026-10-19** (PyAV 19.0.1, libavformat 63.1.102, macOS; scratch directories outside the repo):
  - `av.open(file, options=..., timeout=...)` passes `options` to `avformat_open_input` (see `av/container/core.py`). FFmpeg checks `format_whitelist` after it detects the format and before the demuxer's `read_header`.
  - A refused demuxer raises `av.error.ArgumentError`, with `errno` 22 and `strerror` "Invalid argument". The class subclasses both `FFmpegError` and the builtin `ValueError`, and `e.log` is None.
  - FFmpeg demuxer names are lists separated by commas, and the whitelist matches any one of the names.
    - `container.format.name` is `"mov,mp4,m4a,3gp,3g2,mj2"` for mp4, m4a, mov and 3gp, and `"matroska,webm"` for mkv, webm and mka.
    - An `mp2` file opens as `mp3`, and ADTS opens as `aac`.
  - **With main's options, these crafted files read other files:**

    | File | What happens on main |
    | --- | --- |
    | `.mp4`-named ffconcat list | opens as `concat`, with the neighbour's 2 streams |
    | local `.m3u8` | opens as `hls`, 2 streams |
    | `seq%03d.png` | opens as `image2`, reading 4 files |

    Also on main: a PNG named `.mp4` opens as `png_pipe`, a `.nfo` as `tty` and a `.srt` as `srt`. HLS text in a file named `.mp4` is already `InvalidDataError` (FFmpeg's hls probe requires an m3u8/m3u extension).
  - **What the fd-based opener (card 6) does with each case:**

    | Case | Result |
    | --- | --- |
    | ffconcat | `ArgumentError` |
    | `.m3u8` | `InvalidDataError` |
    | HLS in a file named `.mp4` | `InvalidDataError` |
    | `.nfo` | `InvalidDataError` |
    | `.srt` | `ArgumentError` |
    | `.sdp` | `ArgumentError` |
    | `seq%03d.png` | `ArgumentError` (seen as `png_pipe`) |
    | PNG named `.mp4` | `ArgumentError` |
    | a symlink to the ffconcat list | `ArgumentError` |
    | `not_media.txt` | `InvalidDataError` |
    | missing file, dangling link | `FileNotFoundError(2, 'No such file or directory')` |
    | file with mode 000 | `PermissionError(13, 'Permission denied')` |
    | directory, `/dev/null` | refused by `stat` |

  - **FIFO:** `av.open` on a FIFO blocks forever, timeout or not. `os.stat` and `os.open(..., O_RDONLY | O_NONBLOCK)` both return at once.
  - **mov drefs.** A copy of clean.mp4 was edited so that video track 0's `dref` holds one `alis` entry with absolute path `/x/other.mp4`, `nlvl_from = nlvl_to = 1`, and the file's own `mdat` payload zeroed.
    - Main's options with `enable_drefs=1`: 125 video packets, all decodable, read from the neighbour.
    - Defaults (`enable_drefs=0`): FFmpeg logs "Skipped opening external track" and demuxes 0 video packets.
    - Through `fd:` with `enable_drefs=1` forced on: 0 video packets with cwd = the file's directory, `InvalidDataError` with any other cwd.
  - **FFmpeg source** (`libavformat/*.c` at FFmpeg master, fetched 2026-10-19):
    - `matroskadec.c`, `oggdec.c`, `mpegts.c`, `wavdec.c`, `mp3dec.c`, `aacdec.c` and `flacdec.c` contain no `io_open`, `avio_open` or `avformat_open_input` call.
    - `avidec.c`'s only one opens an in-memory GAB2 subtitle demuxer: only `srt` or `ass`, with the parent's whitelists copied.
    - `mov.c` opens other files only in `mov_open_dref`. That runs only when `enable_drefs` is set (default 0). It refuses absolute paths and paths containing `..` or `:` unless `use_absolute_path` is set (default 0).
    - FFmpeg's matroska demuxer has no code for loading linked segments or ordered-chapter segments from other files.
  - **Unusual names.** `a #1.mp4`, `50% d%03d.mp4`, `what?.mp4`, `réunion é 01.mp4` and `file:z.mp4`, each a copy of clean.mp4, open through the fd as mov.
  - **Encoders in the wheel** that the tests use: `pcm_s16le`, `pcm_s16be`, `flac`, `aac`, `mp2`, `ac3`, `eac3`, `wmav2` (it opens at 44 100 Hz stereo with `bit_rate=128000`), `mpeg4` and `png`. Raw H.264 and HEVC are made by remuxing fixtures, with no encoder.
  - **pytest-timeout is not installed.** Don't add it; the FIFO tests use a thread with a bounded `join`.

## Scope
May change:
- `src/tapesift/media/safe_open.py` (new)
- `src/tapesift/media/probe.py`: the open call becomes `open_media(path)`; `PROBE_TIMEOUT_S` is removed (card 5); the module docstring's sentence about `"file:"` URLs is updated. Keep `import av` and `import av.error` exactly as they are, because tests patch `tapesift.media.probe.av.open`, which is the shared `av` module.
- `src/tapesift/media/decode.py`: the body of `_open` and its comment only.
- `tests/unit/test_safe_open.py` (new)
- `tests/unit/test_probe.py`: only the `PROBE_TIMEOUT_S` import, `test_open_uses_file_url_and_whitelist` (renamed and rewritten per card 5), the assertions in `test_timeout_passed`, and the section comment above them (line 617), which becomes `# --- security: open through a checked fd, fd protocol only, demuxer allow-list (#21) ---`. Nothing else.
- `CHANGELOG.md`: one line under Unreleased → Changed: `- **Security:** media opens through one shared opener: regular files only, read through a checked file descriptor, nine container formats (mov/mp4, matroska/webm, avi, mpegts, wav, mp3, aac, flac, ogg); playlists, concat lists, image sequences, subtitles and other formats are UNREADABLE (#21).`

Must not touch:
- `src/tapesift/media/types.py`, `src/tapesift/media/__init__.py`, `src/tapesift/media/asset_id.py`, `src/tapesift/warning_codes.py`
- `tests/smoke/**` (its 147 tests must pass unchanged), `tests/unit/test_media_types.py`, `tests/unit/test_asset_id.py`, `tests/unit/test_fixtures.py`, `tests/fixtures/**`, `scripts/make_fixtures.py`
- `pyproject.toml`, `uv.lock`, `THIRD_PARTY.md`. No new dependency.
- `docs/**`. The scribe amends 5-probe.md and 6-decode.md after the merge.

## Interfaces touched

### New: `src/tapesift/media/safe_open.py`
```python
ALLOWED_FORMATS: Final = ("mov", "matroska", "avi", "mpegts", "wav", "mp3", "aac", "flac", "ogg")  # card 2
OPEN_TIMEOUT_S: Final = 30.0   # card 3; per open and per demux call; module constant until config.py exists

class UnsafeInputError(OSError):   # card 7
    """open_media refused the file: not a regular file, or a container format FFmpeg may not
    demux here. An OSError, so every stage's `except (FFmpegError, OSError)` maps it to
    UNREADABLE unchanged."""

def open_media(path: Path) -> InputContainer:   # av.container.InputContainer
    """Open one local media file for demuxing. Every stage calls this; nothing else calls av.open.
    Raises UnsafeInputError, OSError (missing, permission) or av.error.FFmpegError (not media).
    Never blocks on a FIFO."""
```
What `open_media` does, in order:
1. `mode = os.stat(path).st_mode`. This follows symlinks (card 4). Any `OSError` propagates unchanged: a missing file or dangling link raises `FileNotFoundError` with `strerror` "No such file or directory", so probe's pinned detail is unchanged.
2. If `not stat.S_ISREG(mode)`, raise `UnsafeInputError(f"not a regular file: {kind}")`. The file is never opened. `kind` comes from a private `_kind(mode) -> str`:

   | Test | `kind` |
   | --- | --- |
   | `S_ISDIR` | `"directory"` |
   | `S_ISFIFO` | `"fifo"` |
   | `S_ISCHR` | `"character device"` |
   | `S_ISBLK` | `"block device"` |
   | `S_ISSOCK` | `"socket"` |
   | anything else | `"unknown type"` |

3. `fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)`. Python already makes it non-inheritable (close-on-exec). An `OSError` propagates.
4. In `try: ... finally: os.close(fd)`:
   1. `mode = os.fstat(fd).st_mode`. If it is not a regular file, raise `UnsafeInputError(f"not a regular file: {_kind(mode)}")`. This catches a swap between steps 1 and 3; `O_NONBLOCK` meant the open in step 3 couldn't block.
   2. `os.set_blocking(fd, True)`.
   3. `return av.open("fd:", options={"protocol_whitelist": "fd", "format_whitelist": ",".join(ALLOWED_FORMATS), "fd": str(fd)}, timeout=OPEN_TIMEOUT_S)`, with exactly these arguments. Call it as `av.open` through the module, so existing monkeypatches keep working. FFmpeg `dup`s the fd, so closing ours in `finally` is safe and leaks nothing.
   4. `except av.error.ArgumentError as e: raise UnsafeInputError("container format not allowed or header invalid") from e`. Every other exception propagates unchanged.

No logging in the opener: no asset ID exists yet, so the caller logs. There is no post-open `container.format.name` check (T1, see Out of scope).

### Changed: `src/tapesift/media/probe.py`
- Before: `PROBE_TIMEOUT_S: Final = 30.0` and `with av.open("file:" + str(path.resolve()), options={"protocol_whitelist": "file"}, timeout=PROBE_TIMEOUT_S) as container:`
- After: `PROBE_TIMEOUT_S` is deleted, and the call is `with open_media(path) as container:`. The `except (av.error.FFmpegError, OSError)` clause and the detail format `f"{type(e).__name__}: {e.strerror or e}"` stay as they are.
- New details:
  - `"UnsafeInputError: not a regular file: <kind>"`
  - `"UnsafeInputError: container format not allowed or header invalid"`
- `asset_id(path)` still runs inside the `with`, after `open_media` returns.

### Changed: `src/tapesift/media/decode.py`
- `_open(asset: AssetInfo) -> InputContainer` keeps its signature.
- Its body becomes `return open_media(Path(asset.path))`, inside the same `except (FFmpegError, OSError) as e: raise DecodeError(WarningCode.UNREADABLE, f"cannot open: {e}") from e`.
- New details:
  - `"cannot open: not a regular file: <kind>"`
  - `"cannot open: container format not allowed or header invalid"`
- Decode now has the 30 s per-demux timeout (card 3).

Future stages (E3 audio, C4 NVDEC) import `open_media`.

## Acceptance
Baseline on main at 989f5c1, measured by the planner on 2026-10-19:
- `uv run pytest -q -m "not gpu"`: `451 passed, 2 deselected`, with 0 skipped and 0 xfailed;
- tests collected: `tests/unit/test_probe.py` 133, `tests/smoke` 147;
- `uv run ruff format --check .`: `51 files already formatted`.

If main moves before the build, the builder re-measures and states the new baseline in the PR.

| Command | Expected |
| --- | --- |
| `uv run pytest tests/unit/test_safe_open.py -q` | `64 passed` |
| `uv run pytest tests/unit/test_probe.py -q` | `133 passed` |
| `uv run pytest tests/smoke -q` | `147 passed` |
| `uv run pytest -q -m "not gpu"` | `515 passed, 2 deselected`, with no `failed`, `error`, `skipped` or `xfailed` |
| `uv run ruff format --check .` | `53 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `git diff --numstat main -- CHANGELOG.md` | `1	0	CHANGELOG.md` |
| `grep -rn "av\.open(" src/tapesift` | exactly one line, in `src/tapesift/media/safe_open.py` |
| `grep -rln "protocol_whitelist\|format_whitelist" src/tapesift` | exactly `src/tapesift/media/safe_open.py` |
| `grep -rn "PROBE_TIMEOUT_S" src tests` and `grep -rn '"file:"' src/tapesift tests/unit/test_probe.py` | each prints nothing (exit 1) |
| `grep -nE "pytest\.skip\|mark\.skip\|importorskip\|mark\.xfail" tests/unit/test_safe_open.py` | prints nothing (exit 1) |
| Command A1 below (new tests against main's probe.py and decode.py) | last line `11 failed in <t>s`; paste it into the PR under How tested |
| `make check` | exits 0 |

Command A1:
```bash
git stash push src/tapesift/media/probe.py src/tapesift/media/decode.py && \
uv run pytest -q \
  "tests/unit/test_safe_open.py::test_probe_refuses_indirection" \
  "tests/unit/test_safe_open.py::test_decode_refuses_indirection" \
  "tests/unit/test_safe_open.py::test_stages_refuse_fifo_without_blocking" \
  "tests/unit/test_safe_open.py::test_stages_pass_allow_list_and_timeout"; \
git stash pop
```
Why all 11 fail on main:
- 3 + 3: main's probe and decode read the neighbour, so nothing is raised;
- 3: main's `av.open` blocks on the FIFO, so the thread is still alive after `join(5)`;
- 2: main's options have no `format_whitelist`, and its decode passes no timeout.

`git diff --name-only main...HEAD` prints exactly:
```text
CHANGELOG.md
src/tapesift/media/decode.py
src/tapesift/media/probe.py
src/tapesift/media/safe_open.py
tests/unit/test_probe.py
tests/unit/test_safe_open.py
```

### `tests/unit/test_safe_open.py`: 64 tests
Conventions used by every test below:
- All crafted files are written to `tmp_path` while the test runs, and no test uses the network.
- In every crafted-input case, `socket.socket.connect` is patched to raise.
- "Neighbour" is `tmp_path / "other.mp4"`, a copy of `tests/fixtures/clean.mp4`.
- `RAW(p, **extra)` means `av.open("file:" + str(p.resolve()), options={"protocol_whitelist": "file", **extra})`, which reproduces main's open.
- `UNSAFE` means `UnsafeInputError` with `str()` equal to `"container format not allowed or header invalid"`.
- `INVALID` means `av.error.InvalidDataError`.
- Audio files are 1 s of silence, muxed by PyAV.

**FIFO pattern.** It is used by every FIFO case:
1. Run the call in a `daemon=True` thread that stores its result or exception.
2. `t.join(5)`, then assert `not t.is_alive()`.
3. In `finally`, if the thread is still alive, unblock it with `try: os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)) except OSError: pass`, then `t.join(5)`.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_allowed_format_opens[<name>]` | 9 | The file opens through `open_media`, and `name in c.format.name.split(",")`. Cases (name: file, muxer, codec, mono 16 kHz): wav: `a.wav`, `wav`, `pcm_s16le`; mp3: `a.mp2`, `mp2`, `mp2`; aac: `a.aac`, `adts`, `aac`; flac: `a.flac`, `flac`, `flac`; ogg: `a.ogg`, `ogg`, `flac`; avi: `a.avi`, `avi`, `pcm_s16le`; mpegts: `a.ts`, `mpegts`, `mp2`; matroska: `a.mkv`, `matroska`, `flac`; mov: `a.m4a`, `mp4`, `aac`. The case IDs are written as a literal list, and one case also asserts `tuple(ids) == ALLOWED_FORMATS`. |
| `test_refused_family[<case>]` | 12 | Card 2's table. `RAW(p)` opens the file as that demuxer (`name in c.format.name.split(",")`). `open_media(p)` raises UNSAFE, except `hevc`, which raises INVALID. `probe(p)` raises `ProbeError` with code `UNREADABLE`. How each file is made: **h264** `raw.h264`, remuxing clean.mp4's video packets with `add_stream_from_template` into the `h264` muxer and skipping packets whose `dts` is None. **hevc** `raw.hevc`, the same from hdr10.mkv into `hevc`. **m4v** `raw.m4v`, 25 64x48 black frames encoded with `mpeg4` into `m4v`. **ac3** and **eac3** `a.ac3` / `a.eac3`, 48 kHz stereo. **mpeg** `a.mpg`, `mpeg` with `mp2`. **aiff** `a.aiff`, `pcm_s16be`. **flv** `a.flv`, `aac` at 44 100 Hz. **asf** `a.wma`, `wmav2` at 44 100 Hz stereo with `bit_rate=128000`. **amr** `a.amr`, `b"#!AMR\n" + bytes([0x3C] + [0] * 31) * 50`. **caf** `a.caf`, `pcm_s16le`. **w64** `a.w64`, `pcm_s16le`. |
| `test_refused_demuxer[<case>]` | 8 | `open_media` raises the pinned error. Each case has the neighbour next to it. **ffconcat_mp4**: `evil.mp4` = `"ffconcat version 1.0\nfile other.mp4\n"` → UNSAFE. **hls_m3u8**: `evil.m3u8` = `"#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXTINF:5,\nother.mp4\n#EXT-X-ENDLIST\n"` → INVALID. **hls_named_mp4**: the same text in `hls.mp4` → INVALID. **image2_sequence**: `seq%03d.png` plus `seq001.png`..`seq003.png`, each a 16x16 PNG muxed by PyAV (`image2`, `png`) → UNSAFE. **png_named_mp4**: that PNG copied to `frame.mp4` → UNSAFE. **tty_nfo**: `art.nfo` = `"hello ansi\n" * 20` → INVALID. **srt**: `subs.srt` = `"1\n00:00:00,000 --> 00:00:01,000\nhello\n\n"` → UNSAFE. **sdp**: `x.sdp` = `"v=0\no=- 0 0 IN IP4 127.0.0.1\ns=x\nc=IN IP4 127.0.0.1\nt=0 0\nm=audio 9 RTP/AVP 0\n"` → UNSAFE. |
| `test_attack_is_live_without_allow_list[<case>]` | 4 | This keeps the refusal tests from passing vacuously: each crafted file really does read the neighbour under main's open. **ffconcat_mp4**: `RAW` opens it as `concat` with 2 streams. **hls_m3u8**: `hls` with 2 streams. **image2_sequence**: `image2`, demuxing 4 video packets. **mov_dref**: `RAW(evil_mov, enable_drefs="1")` demuxes 125 video packets. If a future FFmpeg stops detecting one of these, this test fails and the crafted file has to be redone. |
| `test_mov_dref_not_followed[<case>]` | 2 | `evil.mov` is built in the test by a box rewriter of about 20 lines. It parses `clean.mp4` boxes, recursing into `moov`, `trak`, `mdia`, `minf` and `dinf`. It replaces the first `trak`'s `dref` body with `struct.pack(">II", 0, 1)` plus one `alis` entry, rebuilds the box sizes, and zeroes the `mdat` payload. clean.mp4's top-level order is `ftyp, free, mdat, moov`, so no chunk offsets move. The `alis` body is `u32 0`, then `10 zero bytes`, `u8 0`, `27 zero bytes`, `12 zero bytes`, `u8 9`, `b"other.mp4"` padded to 63 bytes, `16 zero bytes`, `u16 1`, `u16 1`, `16 zero bytes`, `u16 2`, `u16 len("/x/other.mp4")`, the path, and `i16 -1`, `u16 0`. **default**: `open_media(evil_mov)` opens, and demuxing video stream 0 yields 0 packets with `size > 0`. **forced_on**: `monkeypatch.chdir(tmp_path)`; `av.open` is wrapped to add `"enable_drefs": "1"` to the options, then `open_media(evil_mov)` still yields 0 video packets, because the `fd` protocol whitelist blocks the second open. |
| `test_probe_refuses_indirection[<case>]` | 3 | `probe(p)` raises `ProbeError(UNREADABLE)`. **ffconcat_mp4** and **image2_sequence**: detail exactly `"UnsafeInputError: container format not allowed or header invalid"`. **hls_m3u8**: detail exactly `"InvalidDataError: Invalid data found when processing input"`. |
| `test_decode_refuses_indirection[<case>]` | 3 | The same three. `next(PyAVDecoder().iter_frames(asset, None, warn=sink.append))` raises `DecodeError(UNREADABLE)` and `sink == []`. **ffconcat_mp4** and **image2_sequence**: detail exactly `"cannot open: container format not allowed or header invalid"`. **hls_m3u8**: detail starts with `"cannot open: "` and contains `"Invalid data found when processing input"`. `asset` is built by hand: `AssetInfo("tsid1:" + "0" * 64, p, 5.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0), (), ())`. |
| `test_non_regular_refused[<case>]` | 5 | `open_media` raises `UnsafeInputError` with `str()` equal to `"not a regular file: <kind>"`. Cases: **directory** (`tmp_path / "folder.mp4"`, kind `directory`); **fifo** (`os.mkfifo(tmp_path / "pipe.mp4")`, kind `fifo`, FIFO pattern); **char_device** (`Path("/dev/null")`, kind `character device`); **symlink_to_fifo** (`fifo`, FIFO pattern); **symlink_to_char_device** (`character device`). |
| `test_stages_refuse_fifo_without_blocking[<stage>]` | 3 | Uses a FIFO at `tmp_path / "pipe.mp4"` and the FIFO pattern. **probe**: `probe(fifo)` raises `ProbeError(UNREADABLE)` with detail `"UnsafeInputError: not a regular file: fifo"`; this proves `asset_id` never opened it. **frames** and **audio**: `next(iter_frames(...))` and `next(iter_audio(...))` on a hand-built asset at that path, with one video stream and `AudioStreamInfo(1, "aac", None, True)`, raise `DecodeError(UNREADABLE)` with detail `"cannot open: not a regular file: fifo"`. |
| `test_swap_to_fifo_after_stat_is_refused` | 1 | The path is a FIFO, and `tapesift.media.safe_open.os.stat` is monkeypatched to return `os.stat(FIXTURES / "clean.mp4")`, which simulates a swap after step 1. Under the FIFO pattern, `open_media` raises `UnsafeInputError("not a regular file: fifo")` from the `fstat` check. |
| `test_symlink_to_media_opens` | 1 | Card 4. `tmp_path / "link.mp4"` points to `FIXTURES / "clean.mp4"`. `open_media` opens it as mov, and `probe(link).duration_s == 5.0`. |
| `test_open_os_errors_pass_through[<case>]` | 3 | **missing** (`tmp_path / "gone.mp4"`) and **dangling_symlink** raise `FileNotFoundError`. **no_permission** (a copy of clean.mp4 after `chmod(0)`, with mode restored in `finally`) raises `PermissionError`. None of them is an `UnsafeInputError`. |
| `test_other_open_errors_pass_through` | 1 | `open_media(FIXTURES / "not_media.txt")` raises `av.error.InvalidDataError`, not `UnsafeInputError`: only EINVAL is mapped. |
| `test_unusual_names_open[<name>]` | 5 | A copy of clean.mp4 named `a #1.mp4`, `50% d%03d.mp4`, `what?.mp4`, `réunion é 01.mp4` or `file:z.mp4` opens through `open_media` as mov, and `probe(p).duration_s == 5.0`. |
| `test_open_call_exact` | 1 | `av.open` is wrapped with a recorder that calls the real one. One `open_media(FIXTURES / "clean.mp4")` records `args == ("fd:",)` and `kwargs["timeout"] == 30.0`. `kwargs["options"]` with `"fd"` popped equals `{"protocol_whitelist": "fd", "format_whitelist": "mov,matroska,avi,mpegts,wav,mp3,aac,flac,ogg"}`, and the popped value satisfies `.isdigit()`. Also asserts `OPEN_TIMEOUT_S == 30.0`. |
| `test_no_fd_leak` | 1 | `n0 = len(os.listdir("/dev/fd"))` (this works on Linux and macOS). Then 20 rounds of each: `open_media(clean).close()`, `open_media(<ffconcat_mp4>)` raising, `open_media(<FIFO>)` raising, and `open_media(not_media.txt)` raising. Afterwards `len(os.listdir("/dev/fd")) == n0`. |
| `test_stages_pass_allow_list_and_timeout[<stage>]` | 2 | With the same recorder: `probe(clean)` (**probe**) and `next(PyAVDecoder().iter_frames(<hand-built clean asset>, None, warn=sink.append))` (**decode**) each make exactly one `av.open` call, with `args == ("fd:",)` and the exact options and timeout above. |

Count: 9 + 12 + 8 + 4 + 2 + 3 + 3 + 5 + 3 + 1 + 1 + 3 + 1 + 5 + 1 + 1 + 2 = **64**. Card 2 option B keeps 64 (11 + 10 instead of 9 + 12).

## Out of scope
- **A per-file wall-clock limit** that can cancel a syscall stuck in the kernel (hung NAS). This is the Core-lane runner's job, a follow-up from card 3; the lead files it.
- **`full_hash=True` (a future `--full-hash`) on huge or slow files.** It reads the whole file with plain Python I/O and no time bound, so a multi-GB file on a slow mount can take minutes. The default `tsid1` mode reads at most 16 MiB plus the size (ADR 0012). The same per-file runner limit covers it.
- **A post-open `container.format.name` check.** T1: FFmpeg enforces the whitelist before `read_header`, so a check after open would come too late. It would also break the stand-in containers that existing probe and decode tests return from a patched `av.open`. `test_refused_demuxer` and `test_attack_is_live_without_allow_list` already catch a PyAV that silently drops the option.
- Turning on PyAV logging to name the refused demuxer (card 1, option C).
- `format=` on `av.open`. Forcing one demuxer needs the format known in advance.
- A socket test case: macOS limits `AF_UNIX` paths to 104 bytes, and `tmp_path` can be longer. `S_ISSOCK` goes through the same branch as the FIFO and device cases.
- A DTS case (no encoder in the wheel), and a matroska linked-segment case: FFmpeg's matroska demuxer has no code that opens another file, so there is nothing to exercise. `test_mov_dref_not_followed[forced_on]` shows the `fd`-only whitelist blocks any demuxer's second open.
- Passing the opened descriptor to `asset_id` (see Risks). `asset_id.py` and its ADR are M0's.
- E3 and C4 adopting the opener; amending 5-probe.md and 6-decode.md (scribe, after the merge).

## Risks
- **Linux is not run locally.** The `fd` protocol (`libavformat/file.c`) and `O_NONBLOCK` on a FIFO are POSIX behaviour, but the planner observed them on macOS only. The ubuntu CI jobs (3.12 and 3.13) are the proof. If they disagree with macOS, stop and report; don't add a per-OS branch without a card.
- **`asset_id` opens the path a second time.** After `open_media` returns, probe's `asset_id(path)` opens `path` again with Python I/O. If the path is swapped for a FIFO in that window, `asset_id` blocks. If it's swapped for another regular file, the ID and the metadata describe different files. The threat model here is crafted file content, not a local attacker racing renames. Mark it with a `ponytail:` comment in probe.py. Upgrade path: `asset_id` hashes from a file object that `open_media` also checked (an M0/ADR 0012 change, so a card).
- **Opening a device.** A device swapped in between steps 1 and 3 is opened (with `O_NONBLOCK`) before `fstat` refuses it. Opening some devices has side effects, such as a tape rewinding. This takes a race against a local attacker, and step 1 means it never happens otherwise.
- **EINVAL is ambiguous.** An allowed demuxer that rejects a crafted header with `AVERROR(EINVAL)` gets the same detail as a refused format. It is `UNREADABLE` either way, and the detail names both causes (card 1).
- **Detection without the extension** (card 6). A real file in an allowed format whose content probe is weak could become `INVALID`. Observed: none among the 24 media fixtures and 9 allowed-format files. If one shows up, report it with the file; don't put the `file:` URL back.
- **Demuxer names can change with FFmpeg.** `test_allowed_format_opens` and `test_refused_family` fail if a PyAV upgrade renames one. Fix the name; never drop the test.
- **Options are a security surface.** The opener never sets `enable_drefs` or `use_absolute_path`. Adding any key to its options dict needs a card.
- **The decode timeout is new.** PyAV checks its interrupt callback on every I/O call. The 3-hour smoke tests (`test_long_*`) must stay green; if `make smoke` is noticeably slower than on main, report both times in the PR.
- **`test_open_os_errors_pass_through[no_permission]`** assumes tests don't run as root (CI runners don't). Under root it fails loudly, never silently.
- **`filterwarnings = error`.** Any warning raised while muxing in a test fails the suite. Fix the call; never silence it.
- **Existing patches.** `tests/unit/test_probe.py` patches `tapesift.media.probe.av.open`, and `tests/smoke/test_decode.py` patches `av.open`. Both still reach `safe_open`, because it calls `av.open` through the shared module, and the descriptor is still open while the patched call runs. A stand-in container passes straight through, because there is no post-open check. `test_unicode_path_passed_as_str` (smoke) still passes, but FFmpeg now sees `fd:` rather than the Unicode path; `test_unusual_names_open` covers names now.
