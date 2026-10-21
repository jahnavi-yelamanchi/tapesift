# 30. Runner v0 and `tapesift index` (E7)

Issue: #30 (absorbs #11 and #36)   Lane: Core   Status: approved 2026-10-20 (owner, gate 1)
Revisions: 2026-10-20 r3, owner decisions after the two-model council and rebuttal (T3 cards 4-10) and the owner's T2 calls:
- card 4 B: file names `tsid1_<hex>.json` / `sha256_<hex>.json`; `index.json` gets `"layout": 1`; only `assets/` is public;
- card 5 A;
- card 6 A, plus a top-level `"version"` key;
- cards 7 and 8 A;
- card 9 A, with the flag named `--max-media-hours`;
- card 10 A, plus SIGTERM and SIGHUP, signals blocked during writes, and a second signal exits at once;
- card 1 B (two phases in one draft PR; corrected relay, owner 2026-10-20); cards 2, 3, 11 and 12 A;
- card 13: rich is declared by M1;
- E6's `StoreError` exits 2.
Revisions: 2026-10-20 r2, after spec-critic (lead-filtered).
- **Bugs fixed:**
  - the `__main__.py` guard is now in scope, and test drivers are guarded files;
  - the pinned walk order;
  - a copy of a collision-resolved file;
  - the same file under two names, and a deleted collision original;
  - marker-write failures;
  - a bounded model-load wait and a load-time crash;
  - `getsize` moved inside the per-file guard;
  - rich markup off for file names;
  - a parent-death watchdog, and SIGINT ignored from exec;
  - worker stdout sent to stderr;
  - a fresh `index.json` rule, written with E5-style syncs.
- **Gaps closed:** the stage of a pre-stage failure; a retry hint; dry-run duplicates and hours; `--max-hours` accounting; a timeout ceiling plus a no-progress check; malformed markers; logged walk skips with a spec.md 299 edit; a lock against concurrent runs; E5's temp name `.tapesift-<pid>.tmp`; no chmod in tests.
- **Tiers:** cards 4-10 are now T3. Card 13 (rich) is new, T2.
- **Scope:** spec.md lines 212, 217 and 299 are in scope; the ADR 0012 amendment is scribe work.

Planned against the approved M1 interface spec, `docs/specs/25-m1-interfaces.md` at local main 2c6dc88 (owner, gate 1, 2026-10-20). Every M1 name used here is used exactly as M1 defines it: `Config`, `Profile`, `ConfigError`, `ModelLoadError`, `load_config`, `vision_available`, `AssetRecord`, `Provenance`, `ASR`, `VAD`, `VLM`, `Store`, `transcribe_asset`, `caption_asset`, `SileroVAD`, `FasterWhisperASR`, `TransformersVLM`, `OnnxEmbedder`, `LanceStore`, `ASR_MODELS`, `VLM_MODELS`, and the fakes `FakeVAD`, `FakeASR`, `FakeVLM`, `FakeEmbedder`, `MemoryStore`. No M1 name is missing for E7. If a name differs from the approved spec when M1 merges, stop and raise a card. Never adapt silently.

**E5's `write_json` is approved.** `tapesift.schema.output.write_json(record: AssetRecord, path: Path) -> None` comes from `docs/specs/28-schema.md` (approved 2026-10-20, owner, gate 1; commit 896f437), card 3 A. Its temp file is `.tapesift-<pid>.tmp` in the target folder.

**One name comes from a spec that is not approved yet:** `tapesift.store.lance.StoreError(RuntimeError)`, from E6's draft `docs/specs/29-search.md`, card 6: `LanceStore` raises it when `out_dir/store` can't be opened, and E7 maps it to exit 2. It is used only in phase 2 (card 1). If E6 card 6 changes, `cli/index.py` step 6 follows it.

**Amends M1 card 1** (owner, card 4 B, 2026-10-20): the marker path `out_dir/failed/<asset_id>.json` becomes `out_dir/failed/<asset_file_name(asset_id)>`, for example `failed/tsid1_<64 hex>.json`. The marker's content is unchanged. The scribe updates the M1 text.

## Goal
`tapesift index PATH... [--config FILE] [--profile P] [--out DIR] [--max-media-hours H] [--dry-run] [--full-hash] [--json]` does the following:
- walks files and folders in a fixed order;
- runs probe and then the E3 and E4 stages for each file, in one worker process that the runner kills on a wall-clock or no-progress limit (#36);
- upserts each record into the store, then writes `out_dir/assets/<asset_file_name(id)>` (for example `tsid1_<hex>.json`) with E5's `write_json`, last;
- skips finished assets on rerun by asset ID;
- marks `DUPLICATE` only after the full sha256 of both files matches, and never mixes ID modes in one index (#11);
- writes card 1's failed markers with the retry cap;
- shows a rich progress bar;
- ends with a failure summary on stderr (or `--json` on stdout) and exit code 0, 1, 2, 3, or 128 + the signal (130, 143, 129) when stopped by SIGINT, SIGTERM or SIGHUP.

The done-when (spec 341) is that the corrupt fixture fails alone and a rerun skips finished files.

## Read first
- **docs/specs/25-m1-interfaces.md, in full.** It is the source of truth. Especially:
  - card 1 (the failed marker, the cap of 2 attempts per version, StageErrors degrade);
  - card 4 and R7 (`--config`; a path key in a file resolves against the file's folder; `--out` and the default are relative to the current directory);
  - R5 (per-file failures; the JSON is written last, after the upsert);
  - R6 (lazy backend imports);
  - R9 (the captions-off log lines);
  - the stage entry points;
  - the fakes table;
  - Q4 and Q10 B;
  - Out of scope (what M1 leaves to E7).
- **docs/specs/28-schema.md (draft):** card 3 (`write_json`), "Temp name" (`.tapesift-<pid>.tmp`), Interfaces item 5 (file sync, rename, folder sync; E7 sweeps stale temp files), and the `asset.path` privacy description.
- docs/spec.md:
  - lines 37-38 (one bad file never kills a batch; resume by content hash; a kill loses at most the in-flight file);
  - 212 (exit codes);
  - 217 (the CLI line);
  - 287 and 299 (the messy-data rule, `UNREADABLE`, "Skip with the exact reason");
  - 333 (CI indexes all fixtures on CPU);
  - 341 (E7);
  - 730-745 (layers; side effects only in the runner and store; structured logs with `asset_id` and `stage`).
- docs/specs/21-safe-opener.md: card 3 and Risks. Its timeout can't bound a read stuck in the kernel; this runner is the real bound.
- docs/specs/4-media-types.md: the emitter table (`DUPLICATE` is E7's); `StageError` is picklable.
- docs/specs/6-decode.md: house style for this spec.
- ADR 0012 (tsid1 and sha256 IDs; never mix modes; confirm DUPLICATE with a full hash). ADR 0008 (fakes only on the laptop). The ADR 0013 draft, row Q10: `--dry-run` shows files, hours, and skip and resume counts, with no cost line.
- Issues #11, #30, #35 (privacy of paths) and #36.
- Code:
  - `src/tapesift/cli/__init__.py` (`ExitCode`, `app`, `JsonOption`);
  - `src/tapesift/__main__.py`;
  - `src/tapesift/cli/doctor.py` (`Probes`, `diagnose`, `pick_profile`);
  - `src/tapesift/media/probe.py` (`probe(path, *, full_hash=False)`);
  - `src/tapesift/media/asset_id.py` (`asset_id(path, *, full=False)`);
  - `src/tapesift/warning_codes.py`;
  - `tests/smoke/conftest.py`;
  - `tests/unit/test_fixtures.py` (it parses only the code column of the messy-data table);
  - `tests/fixtures/manifest.json`.
- **Observed by the planner on 2026-10-20** (macOS, CPython 3.12, scratch folder under /tmp):
  - **Walk order.** `os.walk` top-down, with `dirnames.sort()` and `sorted(filenames)` over `in/{b/z.mp4, a/y.mp4, B.mp4, é.mp4, a.mp4}`, yields `['in/B.mp4', 'in/a.mp4', 'in/é.mp4', 'in/a/y.mp4', 'in/b/z.mp4']`: a folder's files come before its subfolders.
  - **Locking.** `fcntl.flock(LOCK_EX | LOCK_NB)` on a second descriptor of the same lock file, in the same process, raises `BlockingIOError` (errno 35). So a lock test needs no second process.
  - **SIGINT in a spawned child.** With the parent's SIGINT set to `SIG_IGN` around `Process.start()` (spawn) and restored right after, the child's `signal.getsignal(SIGINT)` is `1` (`SIG_IGN`) from interpreter start, and the parent's handler is `default_int_handler` again. Python doesn't install its KeyboardInterrupt handler when SIGINT is ignored at start.
  - **rich.** `rich` 15.0.0 is installed (typer 0.27.3 depends on it). typer has no public progress API: `typer.rich_utils` is private help formatting. The owner decided M1 declares rich as a direct dependency (card 13); E7 uses it as declared.
  - `typer.Option` has no `min_open` parameter, so `--max-media-hours > 0` is checked in the command.
  - `src/tapesift/__main__.py` calls `main()` without an `if __name__ == "__main__"` guard. Under `python -m tapesift`, spawn re-imports the main module in the child as `__mp_main__`, which would run the CLI again inside the worker. This PR adds the guard (Scope).
  - `tests/` has no `__init__.py`. With M1's `pythonpath = ["."]`, `tests.fakes` and `tests.runner_setups` import as namespace modules, and a spawned child inherits the parent's `sys.path`.
  - `tests/fixtures/` holds 25 fixtures plus `manifest.json`, so a walk of the folder sees 26 files.

## Scope
May change:
- New: `src/tapesift/runner/__init__.py` (a one-line docstring), `src/tapesift/runner/run.py`, `src/tapesift/runner/report.py`.
- New: `src/tapesift/pipeline/__init__.py` (a one-line docstring), `src/tapesift/pipeline/index.py`.
- New: `src/tapesift/cli/index.py`.
- `src/tapesift/cli/__init__.py`: two lines after `doctor` and before `def main()`, exactly:
  ```python
  from tapesift.cli.index import index  # noqa: E402  (needs ExitCode, app and JsonOption above)
  app.command()(index)
  ```
- `src/tapesift/__main__.py`: the bare `main()` becomes `if __name__ == "__main__":` followed by an indented `main()`. Nothing else. `tests/unit/test_cli.py::test_python_dash_m_entry_point` still passes unchanged.
- New tests:
  - `tests/unit/test_runner_plan.py`
  - `tests/unit/test_pipeline_index.py`
  - `tests/smoke/test_runner_isolation.py`
  - `tests/smoke/test_index_fixtures.py`
  - `tests/smoke/test_index_models.py` (`model` marker)
  - `tests/runner_setups.py`: a support module, not a test file. It holds the module-level `Load` functions and the store spy that tests pass to the runner, importable by name in a spawned worker.
- `docs/spec.md`: lines 212, 217 and 299 only, exactly as under "docs/spec.md edits". The 212 and 217 texts follow the decided cards 7, 9 and 10.
- `CHANGELOG.md`: one line under Unreleased, Added: `- \`tapesift index\`: per-file worker with wall-clock and no-progress limits, resume by asset ID, DUPLICATE confirmed by full hash, failed-file markers with a retry cap, progress bar, end-of-run summary and \`--json\`; flags \`--config\`, \`--profile\`, \`--out\`, \`--max-media-hours\`, \`--dry-run\`, \`--full-hash\` (#30, #11, #36).`

Must not touch:
- `src/tapesift/config.py`, `src/tapesift/hub.py`, `src/tapesift/schema/**`, `src/tapesift/audio/**`, `src/tapesift/vision/**`, `src/tapesift/store/**`, `src/tapesift/media/**`, `src/tapesift/warning_codes.py`, `src/tapesift/cli/doctor.py`.
- `tests/fakes.py`, `tests/contract/**`, `tests/fixtures/**`, every existing test file, `scripts/**`.
- `pyproject.toml`, `uv.lock`, `Makefile`, `.github/**` (E3 adds the `models` job, Q4), `AGENTS.md`, `CLAUDE.md`, `README.md` (E9).
- `docs/adr/**`. The ADR 0012 amendment from card 8 is the scribe's, after the council decides.

Anything else is a card, not an edit.

**Separate scribe work, not in this diff:**
- the ADR 0012 Consequences line (card 8);
- docs/status.md;
- telling E5 that `asset.path` is absolute (card 5), so its schema description matches.

## Interfaces touched
Before: none. After: the files below. Docstrings and comments are part of the contract.

### `src/tapesift/runner/report.py`
```python
"""The end-of-run summary of `tapesift index`: per-file results, counts, the exit code, the
human text (stderr) and the --json document (card 6). Pure: no I/O."""

Status = Literal["indexed", "pending", "skipped", "duplicate", "failed", "failed_before", "deferred"]
STATUSES: Final[tuple[Status, ...]] = get_args(Status)  # this order, everywhere


@dataclass(frozen=True, slots=True)
class FileResult:
    path: str  # absolute (card 5); display form: undecodable bytes as backslash escapes
    status: Status
    asset_id: str | None  # None when the file was not probed or probe failed
    duration_s: float | None  # AssetInfo.duration_s; feeds media_hours; not in --json
    code: WarningCode | None = None  # UNREADABLE (probe-phase failures), DUPLICATE
    stage: str | None = None  # failed: the stage that failed (a StageName)
    detail: str | None = None  # the exact reason, e.g. "same content as /a/clean.mp4"


@dataclass(frozen=True, slots=True)
class Summary:
    out_dir: str  # os.path.abspath(cfg.out_dir)
    id_mode: Literal["tsid1", "sha256"]
    dry_run: bool
    interrupted_by: int | None  # the signal number (SIGINT, SIGTERM, SIGHUP); None: ran to the end
    max_media_hours: float | None
    total: int  # entries the walk produced; len(files) < total only when interrupted
    files: tuple[FileResult, ...]  # walk order

    @property
    def interrupted(self) -> bool: ...  # interrupted_by is not None
    def counts(self) -> dict[Status, int]: ...  # every status, in STATUSES order, zeros included
    def media_hours(self) -> float: ...  # sum of duration_s (None as 0) over indexed, or pending in a dry run, / 3600
    @property
    def exit_code(self) -> int: ...  # 1 if any failed or failed_before, else 0 (R5); interrupted is the CLI's


def to_dict(summary: Summary) -> dict[str, object]: ...
def render(summary: Summary) -> str: ...
```

`to_dict(summary)` gives exactly these keys, in this order:
- `"version": 1`, first. This is the format version of the `index --json` document, bumped only on a breaking change (owner, card 6);
- `"out_dir"`, `"id_mode"`, `"dry_run"`, `"interrupted"`, `"max_media_hours"`, `"total"`;
- `"counts"`: `summary.counts()`;
- `"media_hours"`: `round(summary.media_hours(), 4)`;
- `"files"`: one entry per file, each exactly `{"path", "status", "asset_id", "code", "stage", "detail"}`. `code` is the string value or null.

`render(summary)` gives lines joined by `"\n"`, with no trailing newline. In order:
1. The headline:
   - Normal run: `f"indexed {c['indexed']}, skipped {c['skipped']}, duplicate {c['duplicate']}, failed {c['failed']}, failed before {c['failed_before']}, deferred {c['deferred']} ({summary.total} files, {h:.2f} h of media)"`.
   - Dry run: `f"dry run, nothing written: {c['pending']} to index ({h:.2f} h of media), skipped {c['skipped']}, duplicate {c['duplicate']}, failed {c['failed']}, failed before {c['failed_before']}, deferred {c['deferred']} ({summary.total} files)"`.
2. A section for each non-empty status among `failed`, `failed_before` and `duplicate`, in that order. The header is `failed:`, `failed before:` or `duplicate:`. Then one line per file, in walk order: `f"  {r.path}{f' ({r.stage})' if r.stage else ''}: {f'{r.code} ' if r.code else ''}{r.detail}"`. The `failed before:` section ends with `f"  to retry, delete their markers in {summary.out_dir}/failed/"`. Card 1 fixes each detail line exactly, so the hint is a separate line.
3. When `deferred > 0`: `f"stopped by --max-media-hours {summary.max_media_hours:g}: {c['deferred']} files left for the next run"`.
4. When `interrupted`: `f"interrupted by {signal.Signals(summary.interrupted_by).name} after {len(summary.files)} of {summary.total} files; rerun to resume"`.

### `src/tapesift/runner/run.py`
```python
"""E7 runner v0 (spec 37-38, M1 R5 and card 1, #11, #36): walk the inputs, run each file in one
killable worker process, resume by asset ID, write out_dir, and return the Summary. The only
module with side effects on out_dir. Imports no backend: models load in the worker via `load`."""

IdMode = Literal["tsid1", "sha256"]
StageName = Literal["probe", "hash", "worker", "asr", "vlm", "record", "store", "write"]
# "worker": inside the worker, before the analysis reported its first stage
StageSink = Callable[[StageName], None]
Beat = Callable[[], None]  # "still making progress"; resets the no-progress limit (card 3)
Analyze = Callable[[AssetInfo, StageSink, Beat], AssetRecord]  # runs in the worker
Load = Callable[[Config], Analyze]
"""Runs once in each worker; builds the models. A module-level function, because it is pickled
by reference into the spawned worker. Raises ModelLoadError when models can't load."""

MAX_ATTEMPTS: Final = 2  # card 1: per tapesift version
INDEX_FILE: Final = "index.json"
LOCK_FILE: Final = ".lock"
ASSETS_DIR: Final = "assets"
FAILED_DIR: Final = "failed"
TEMP_GLOB: Final = ".tapesift-*.tmp"  # E5's write_json temp name, also used by _write_small_json
KILL_JOIN_S: Final = 5.0  # wait after SIGKILL before abandoning a worker
BEAT_EVERY_S: Final = 0.25  # the worker sends at most one beat message per interval
LAYOUT: Final = 1  # index.json "layout"; card 4
ASSET_FILE_RE: Final = re.compile(r"(?:tsid1|sha256)_[0-9a-f]{64}\.json")  # fullmatch


def asset_file_name(asset_id: str) -> str:
    """File name for an asset or marker: the ID with its ":" replaced by "_" (card 4 B), e.g.
    "tsid1_<64 hex>.json". The canonical ID, with ":", lives only inside the JSON."""
    return asset_id.replace(":", "_", 1) + ".json"


class Marker(TypedDict):
    path: str
    stage: str
    exception: str
    error: str
    attempts: int
    tapesift: str


@dataclass(frozen=True, slots=True)
class Limits:
    """Per-file limits (card 3). Module defaults; not config keys in v0.1."""

    probe_s: float = 120.0  # probe, including the tsid1 hash (at most 16 MiB read)
    hash_bytes_per_s: float = 10 * 2**20  # full-hash reads get size / this extra seconds
    load_s: float = 3600.0  # a worker loading models (first-run downloads included)
    index_min_s: float = 600.0
    index_per_media_s: float = 5.0  # x duration_s
    index_max_s: float = 43_200.0  # 12 h ceiling; also the limit when duration_s is None
    stall_s: float = 1800.0  # index phase: kill after this long with no message from the worker

    def probe_deadline(self, size_bytes: int, *, full: bool) -> float:
        return self.probe_s + (size_bytes / self.hash_bytes_per_s if full else 0.0)

    def index_deadline(self, duration_s: float | None) -> float:
        if duration_s is None:
            return self.index_max_s
        return min(self.index_min_s + self.index_per_media_s * duration_s, self.index_max_s)


class Interrupted(KeyboardInterrupt):
    """Raised by the handlers from install_interrupt_handlers; carries the signal number."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


INTERRUPT_SIGNALS: Final = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)  # card 10


def install_interrupt_handlers() -> Callable[[], None]:
    """Each of INTERRUPT_SIGNALS raises Interrupted(signum). Returns a function that restores the
    previous handlers. Called by the CLI, not by run_index."""


def exit_on_next_signal(signum: int) -> None:
    """After the first interruption: any further INTERRUPT_SIGNALS calls os._exit(128 + signum)
    at once (card 10: a second signal while the summary prints exits immediately)."""


class OutDirError(Exception):
    """out_dir can't be used: the other ID mode (#11), an index file this version can't read,
    or another run holds the lock. The CLI exits 2."""


def walk(paths: Sequence[Path]) -> list[Path | FileResult]: ...
@contextmanager
def open_out_dir(out_dir: Path, mode: IdMode, *, create: bool) -> Iterator[None]: ...
def scan_assets(assets_dir: Path) -> dict[str, str]: ...  # asset id -> recorded asset.path
def read_marker(path: Path) -> Marker | None: ...
def retry_allowed(marker: Marker | None, version: str) -> bool: ...
def next_attempts(marker: Marker | None, version: str) -> int: ...
def run_index(
    paths: Sequence[Path],
    cfg: Config,
    *,
    load: Load,
    open_store: Callable[[Config], Store] | None,
    full_hash: bool = False,
    max_media_hours: float | None = None,
    limits: Limits | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> Summary:
    """open_store None is a dry run: nothing is written, nothing is locked, the store isn't
    opened, and the worker never calls load. progress(done, total, current) is called before
    each file, and once more with (total, total, "") at the end. Raises OutDirError,
    ModelLoadError, or OSError when out_dir can't be prepared. KeyboardInterrupt is caught: the
    worker is killed and the partial Summary is returned with interrupted_by set (the
    Interrupted signum, or SIGINT for a plain KeyboardInterrupt). Any other error from
    open_store (E6's StoreError) propagates."""
```

**`walk(paths)`.** Each PATH, in the order given:
- `a = Path(os.path.abspath(p))`. That's absolute and normalized, with no symlink resolution (card 5).
- If `os.path.isdir(a)`: `os.walk(a, onerror=..., followlinks=False)`, top-down. Each folder's files come before its subfolders (observed).
  - Sort `dirnames` in place.
  - The files are `sorted(filenames)`. Sorting is by code point, with no Unicode normalization.
  - Entries whose name starts with `"."` are dropped, both folders and files, and each one logs INFO `f"skipping hidden {display(path)}"` (card 11, spec.md 299 edit). A skipped folder logs once, not once per file inside it.
  - Symlinked files are included; symlinked folders are not entered.
  - `onerror(e)` appends `FileResult(display(e.filename), "failed", None, None, UNREADABLE, None, f"cannot list folder: {e.strerror}")` at that point in the order.
- Otherwise `a` is yielded as a file, even if it is hidden or not a regular file. Probe refuses non-regular files (#21).
- `walk(paths, exclude=out_dir)` (r4): a folder whose resolved path is `out_dir`, or is under it, is not entered, and logs INFO `skipping index folder <path>`. So `tapesift index . --out ./out` never records failures for its own files.
- Entries are deduplicated by `str` path, keeping the first. Different strings for the same file (case-insensitive file systems, NFC and NFD spellings, links) are caught later by `samefile`.
- A path whose `str` can't be encoded as strict UTF-8 becomes `FileResult(display(a), "failed", None, None, UNREADABLE, None, "file name is not valid UTF-8")`.
- `display(p) = os.fsencode(p).decode("utf-8", "backslashreplace")`.

**`open_out_dir(out_dir, mode, *, create)`.** A context manager.
1. **Lock (card 4).** If `create`: `mkdir(parents=True, exist_ok=True)`, then `fd = os.open(out_dir / LOCK_FILE, O_RDWR | O_CREAT)` and `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. A `BlockingIOError` raises `OutDirError(f"{out_dir} is in use by another tapesift index run")`. The lock is held until the context exits. A dry run takes no lock.
2. **Mode.**
   - `index.json` absent: fresh.
   - `{"layout": 1, "id_mode": mode}`: OK.
   - The other known mode: `OutDirError(f"{out_dir} is a {existing} index; this run uses {mode} IDs. Rerun {'with' if existing == 'sha256' else 'without'} --full-hash, or use another --out.")`.
   - Empty, unparsable, a `layout` other than 1, or a missing or unknown `id_mode`: fresh if `assets/` and `failed/` hold no file matching `ASSET_FILE_RE` (a crash while creating the index). Otherwise `OutDirError(f"{out_dir / INDEX_FILE}: not an index this version of tapesift can resume; use another --out.")`.
3. If `create`:
   - make `assets/` and `failed/`;
   - if fresh, write `{"layout": 1, "id_mode": mode}` with `_write_small_json`;
   - unlink every `TEMP_GLOB` file in `out_dir`, `assets/` and `failed/` (left by a hard kill).
4. If not `create`, nothing on disk changes.

**`_write_small_json(path, obj)`** (private; markers and `index.json` only; asset JSON is E5's `write_json`):
- `json.dumps(obj, ensure_ascii=False, indent=2) + "\n"` goes to `path.with_name(f".tapesift-{os.getpid()}.tmp")`;
- `os.fsync` the file, `os.replace`, then `os.fsync` the folder. A folder fsync `OSError` is a WARNING, as in E5;
- the temp file is unlinked on any error, and the error propagates.

**`scan_assets(assets_dir)`.** For each file in `sorted(assets_dir.glob("*.json"))` whose name fullmatches `ASSET_FILE_RE`:
- `doc = json.loads(read_text(encoding="utf-8"))`;
- `aid, p = doc["asset"]["id"], doc["asset"]["path"]`;
- keep it only if both are `str` and `asset_file_name(aid) == f.name`. The ID inside the JSON is trusted; the name is only checked against it.

Any `OSError`, `ValueError`, `KeyError` or `TypeError` logs one WARNING, `f"ignoring unreadable {f.name}: {type(e).__name__}"`, and leaves that asset out. A missing folder gives `{}`.

**Resume rule (coordination with E5):** an asset is done only when a parseable JSON with its ID exists and records that ID and a path. Store rows alone never count. An asset upserted but missing its JSON (a crash between `upsert` and `write_json`'s rename), or with a truncated JSON, is re-indexed. `upsert` is idempotent (M1), and `write_json` replaces the file. JSON Schema validation is not run here: `jsonschema` is a dev dependency only.

**Failed markers (card 1, path amended by card 4 B).** The path is `out_dir/failed/<asset_file_name(asset_id)>`, written with `_write_small_json`.
- The content is exactly `Marker`: `{"path", "stage", "exception", "error": "<Type>: <message>", "attempts", "tapesift"}`.
- `read_marker` returns `None` for a missing file. It also returns `None`, with one WARNING `f"ignoring malformed marker {path.name}"`, when the JSON is unparsable, the keys aren't exactly those six, `attempts` isn't an `int` (not a `bool`) of at least 1, or any other value isn't a `str`.

| Function | Rule |
| --- | --- |
| `retry_allowed(m, v)` | True if `m is None`, or `m["tapesift"] != v`, or `m["attempts"] < MAX_ATTEMPTS` |
| `next_attempts(m, v)` | 1 if `m is None` or `m["tapesift"] != v`, else `m["attempts"] + 1` |

**The worker (cards 2 and 3).**
- **Start.** `ctx = multiprocessing.get_context("spawn")` and a duplex `Pipe()`. Then `Process(target=_worker_main, args=(child_conn, cfg, load if not dry_run else None), daemon=True)`. The parent runs `start()` inside `_signals_deferred()` (below), so a signal during a respawn is recorded, raised after `self.proc` is set, and stops the run (the worker is then killed); it is not lost. The child sets SIGINT, SIGTERM and SIGHUP to `SIG_IGN` as the first line of `_worker_main` (r4: not inherited from the parent, because the parent's handlers are Python functions, which exec resets to default). A terminal hangup or Ctrl-C reaches the parent, and the parent kills the worker (card 10). After `start()`, the parent closes `child_conn`.
- **`_worker_main`, in order:**
  1. `os.dup2(2, 1)` and `sys.stdout = sys.stderr`. Anything a library prints goes to stderr, so `--json` stdout stays clean.
  2. Start a daemon watchdog thread. It records `os.getppid()`, and `os._exit(0)` when that changes, checking every 1 s. That way a worker never outlives a killed parent, even mid-analysis.
  3. Install a logging handler on the root logger at INFO. It sends `("log", name, levelno, message, asset_id, stage)`, under a lock.
  4. Import `tapesift.media.probe` and `tapesift.media.asset_id` here.
  5. If `load` is set, `analyze = load(cfg)`. A `ModelLoadError` replies `("load_error", str(e))` and returns. Then reply `("ready",)`.
  6. Loop on `conn.recv()`. `EOFError` returns. Requests:

| Request | Reply |
| --- | --- |
| `("probe", path, full_hash)` | `("asset", probe(path, full_hash=full_hash))`. A `ProbeError` gives `("probe_error", e.warning.detail)`. Any other `Exception` gives `("error", "probe", type name, f"{type}: {e}")`. |
| `("hash", path)` | `("full_id", asset_id(path, full=True))`. An `Exception` gives `("error", "hash", ...)`. |
| `("index", AssetInfo)` | `("record", analyze(asset, on_stage, beat))`. `on_stage` sends `("stage", name)`. `beat` sends `("beat",)` at most once per `BEAT_EVERY_S`. An `Exception` gives `("error", <last stage, "worker" before the first>, ...)`. |

  Exceptions cross the pipe as strings only.
- **Parent side, `_ask(request, limit_s, stall_s=None)`.** It sends, then loops on `conn.poll(min(deadline, last_message + stall_s) - now)`:
  - a `log` message is re-emitted with `logging.getLogger(name).log(levelno, message, extra={"asset_id": ..., "stage": ...})`;
  - a `stage` message records the last stage (starting at `"probe"`, `"hash"` or `"worker"` by request);
  - any message (`beat` included) resets the stall clock;
  - the first other message is the reply.
  - Past the deadline, raise a private `_Timeout(f"timed out after {limit_s:g} s")`. Past the stall limit, raise `_Timeout(f"no progress for {stall_s:g} s")`. `stall_s` applies to `index` requests only.
  - `EOFError` or `OSError` on `recv` raises `_Crashed(exitcode)`, after `proc.join(KILL_JOIN_S)`.
  - On `_Timeout` or `_Crashed`: `proc.kill()` and `join(KILL_JOIN_S)`. If it is still alive, log the WARNING `f"worker {pid} did not exit after SIGKILL; abandoning it"`. Then close the connection. The next request starts a new worker.
- **Ready wait** (every start, restarts included). `conn.poll` with `limits.load_s`.
  - `("ready",)`: go on.
  - `("load_error", m)`: `ModelLoadError(m)`.
  - EOF: `ModelLoadError(f"worker exited with code {exitcode} while loading models")`.
  - Past `load_s`: kill, then `ModelLoadError(f"models did not load within {load_s:g} s")`.
  - `log` messages are re-emitted meanwhile.
  - A `ModelLoadError` propagates out of `run_index`. Written JSONs and markers stay valid.
- **End.** `run_index` closes the connection (the worker sees EOF), then `join(KILL_JOIN_S)`, and `kill()` if needed. No `Process` or `Connection` is left open (`filterwarnings = error`).

**`run_index`, in order.** `mode = "sha256" if full_hash else "tsid1"`. `out = cfg.out_dir`. `dry = open_store is None`. `v = tapesift.__version__`. `L = limits or Limits()`.
1. Enter `open_out_dir(out, mode, create=not dry)` for the whole run. `indexed = scan_assets(out / ASSETS_DIR)` (asset ID to path), and `by_path` is its inverse.
2. `store = open_store(cfg)` unless dry. Start the worker. `entries = walk(paths)`. `hours = 0.0`. `full: dict[str, str]` caches full IDs by path.
3. For each entry `i`, call `progress(i, total, name)`, then:
   1. A `FileResult` entry is appended as it is.
   2. **Budget (card 9).** If `max_media_hours is not None and hours >= max_media_hours * 3600`, this entry and every later file become `FileResult(display, "deferred", None, None)`, unprobed; walk-level `FileResult` entries in that tail keep their own status (r4). The loop ends.
   3. **Signals are blocked during writes (card 10).** The parent's side effects run inside `_signals_deferred()`, which swaps the Python handlers of `INTERRUPT_SIGNALS` for a recorder inside its `try` (r4: not `pthread_sigmask`, which masks only the calling thread, so a signal the OS hands to another thread would run the handler mid-write), restores every old handler in `finally`, then re-raises the recorded signal (TERM, then HUP, then INT if several arrived). Main thread only. These are the changed-file delete (step 6), the upsert, `write_json`, the marker unlink and the map updates (step 10), and every marker write. A signal that arrives meanwhile is raised right after, so a JSON, a marker and the store never disagree because of a signal.
   4. **Per-file guard.** Everything for this file runs inside one `try`. Any `Exception` gives a failed result, with the current stage and `detail=f"{type(e).__name__}: {e}"`, plus the marker for the final ID when one is known (R5). A marker-write `OSError` logs the ERROR `f"cannot write failed marker for {p}: {e}"` and is swallowed. One bad file never fails the batch.
   5. **Probe.** `_ask(("probe", p, full_hash), L.probe_deadline(os.path.getsize(p) if full_hash else 0, full=full_hash))`. `getsize` is inside the guard; its `OSError` is failed `UNREADABLE` with `detail=e.strerror`.
      - `_Timeout`: failed, `UNREADABLE`, `stage="probe"`, its message.
      - `_Crashed`: failed, `stage="probe"`, `detail=f"WorkerCrashed: worker exited with code {exitcode}"`.
      - `probe_error`: failed, `UNREADABLE`, the detail.
      - `error`: failed, `stage="probe"`, the detail.
      - No marker in any of these: there is no asset ID.
   6. **Resolve the ID (#11, cards 8 and 12).** `fid(path)` is the cached full ID, through `("hash", path)` with `L.probe_deadline(getsize(path), full=True)`. A timeout, crash or error inside it fails this file with `stage="hash"` (`UNREADABLE` for a timeout) and no marker.
      1. **A collision-resolved file, unchanged.** In `tsid1` mode, if `by_path.get(p)` starts with `"sha256:"` and `fid(p)` equals it: skipped. This holds even when the original tsid1 file is gone.
      2. `x = asset.id`. Then `match(x)`, with `q = indexed.get(x)` (in a dry run, the IDs planned so far count too):
         - `q is None`: new, under `x`.
         - `q == p`, or `q` exists and `os.path.samefile(p, q)`: skipped. The detail is None when `q == p`, else `f"same file as {q}"`. The same file under another name is never a duplicate of itself.
         - `q` doesn't exist (`not os.path.exists(q)`): skipped, `detail=f"already indexed as {q}"` (card 12).
         - `x` starts with `"sha256:"`: duplicate, `code=DUPLICATE`, `detail=f"same content as {q}"`.
         - `x` is tsid1: if `fid(p) == fid(q)`, duplicate as above. Otherwise, or when `q` exists but can't be hashed (r4: that is not a match and does not fail the new file), it's a collision: log the WARNING `f"tsid1 collision: {p} and {q} share {x} but their sha256 differ; indexing {p} as {fid(p)}"`, set `asset = dataclasses.replace(asset, id=fid(p))`, and apply `match(fid(p))` once. A file that copies an earlier collision-resolved file is therefore a duplicate of it, never an overwrite.
   7. **Changed file.** Not in a dry run. `old = by_path.get(p)`. If `old` is set and isn't the final ID (or this file is a duplicate or a moved skip): stage `store`, `store.delete(old)`, unlink `assets/<asset_file_name(old)>`, and drop `old` from both maps. This runs before indexing, so a crash leaves nothing stale.
   8. Duplicates and skips end here.
   9. **Retry cap.** `m = read_marker(failed/<asset_file_name(final id)>)`. If `not retry_allowed(m, v)`: failed_before, `detail=f"failed before ({m['attempts']} attempts on {v}); not retried"`.
   10. **Dry run:** pending. Record the final ID as planned, so later copies are duplicates, and `hours += duration_s or 0`.
   11. **Index.** `_ask(("index", asset), L.index_deadline(asset.duration_s), stall_s=L.stall_s)`.
       - `record`: stage `store`, `store.upsert(record)`. Then stage `write`, `write_json(record, out / ASSETS_DIR / asset_file_name(record.asset.id))`, last (M1 R5, E5 card 3). Then unlink the marker, update both maps, and count indexed: `hours += duration_s or 0`, plus one INFO log `f"indexed {p}"`.
       - `_Timeout`: the marker gets `exception="WorkerTimeout"`, `error=f"WorkerTimeout: {message}"` and the last stage.
       - `_Crashed`: `exception="WorkerCrashed"`, `error=f"WorkerCrashed: worker exited with code {exitcode}"` and the last stage.
       - `error`: its stage, type and message.
       - Each of these is a failed result whose detail is the marker's `error`, with `attempts = next_attempts(m, v)`.
4. `progress(total, total, "")`. Return the `Summary`.

**`--max-media-hours` accounting (card 9).** `hours` counts `duration_s` (None as 0) of files indexed in this run, or planned in a dry run. Skipped, duplicate, failed and failed_before files don't count. The check runs before each probe, so the file that crosses H finishes; nothing is cut mid-file.

Every runner log line has `extra={"asset_id": <id or None>, "stage": <stage or None>}` (spec 735).

### `src/tapesift/pipeline/index.py`
```python
"""Per-asset glue (spec 732: cli -> pipeline -> stages): resolve the config (R9), build the
worker's backends, and turn one AssetInfo into one AssetRecord (R5). Real backend modules are
imported inside the functions that build them (R6)."""


@dataclass(frozen=True, slots=True)
class Backends:
    decoder: Decoder
    vad: VAD
    asr: ASR
    vlm: VLM | None  # None: captions off (R9)


def resolve_config(cfg: Config, *, probes: Probes | None = None) -> Config: ...
def load_backends(cfg: Config) -> Backends: ...
def index_asset(
    asset: AssetInfo, on_stage: StageSink, beat: Beat, *, backends: Backends, cfg: Config
) -> AssetRecord: ...
def load(cfg: Config) -> Analyze: ...  # functools.partial(index_asset, backends=load_backends(cfg), cfg=cfg)
def open_store(cfg: Config) -> Store: ...  # LanceStore(cfg, OnnxEmbedder(cfg))
```

**`resolve_config`** returns `cfg.model_copy(update=...)` with:
- `profile`: `cfg.profile`, or, when that is None, `diagnose(probes or Probes(), Path.cwd(), __version__).profile` (doctor's `pick_profile`, with nvidia-smi timeouts).
- `vlm.backend` (R9):
  - `"auto"` becomes `"transformers"` if `vision_available()`. Otherwise it becomes `"none"`, with one WARNING: `captions off: install "tapesift[vision]"`.
  - `"transformers"` without the extra raises `ModelLoadError('vlm.backend = "transformers" needs the vision extra: install "tapesift[vision]"')`.
  - `"none"` logs one INFO line: `captions off (vlm.backend = "none")`.
- `vision_available` is called as a module attribute of `tapesift.pipeline.index`, so tests can patch it.

**`load_backends`** builds `PyAVDecoder()`, `SileroVAD(cfg)`, `FasterWhisperASR(cfg)`, and `TransformersVLM(cfg)` only when `cfg.vlm.backend == "transformers"`. The imports are local. It runs in the worker only.

**`open_store`** has local imports. It runs in the parent only.

**`index_asset`** (M1 R5, Provenance rules). It wraps `backends.decoder` in a private `_BeatingDecoder`, which satisfies `Decoder` and calls `beat()` before yielding each frame or chunk. The stages are given that wrapper, so a stuck read stops the beats (card 3).
1. `on_stage("asr")`.
   - If `asset.audio`: call `transcribe_asset(asset, decoder, vad, asr, cfg, warn=w.append)`. `asr_id = asr.id`, unless a `LOW_SPEECH` warning arrived in that call, in which case it is None.
   - A `StageError` `e`: no utterances, `asr_id = None`, and `e.warning` goes on the record. Warnings sent before the error are kept.
   - No audio: `asr_id = None`, and the stage isn't called.
2. `on_stage("vlm")`.
   - If `asset.video is not None and backends.vlm is not None`: call `caption_asset(...)`. Then `vlm_id = vlm.id` and `prompt = cfg.vlm.prompt`.
   - A `StageError`: no captions, both None, and the warning goes on the record.
   - Otherwise both are None, and no warning code is added (R9).
3. `on_stage("record")`. Return `AssetRecord(asset, tuple(utterances), tuple(captions), tuple(warnings), Provenance(__version__, asr_id, vlm_id, prompt))`.

Any non-`StageError` propagates; the runner fails the asset at the last stage.

### `src/tapesift/cli/index.py`
```python
def index(
    paths: Annotated[list[Path], typer.Argument(exists=True, help="Files or folders to index.")],
    config: Annotated[Path | None, typer.Option("--config", help="Config file (default ./tapesift.toml).")] = None,
    profile: Annotated[Profile | None, typer.Option("--profile", help="cpu, gpu or server (default: doctor picks).")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Index folder, relative to the current directory.")] = None,
    max_media_hours: Annotated[float | None, typer.Option("--max-media-hours", help="Stop starting new files after H hours of media.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Probe and print the plan; write nothing.")] = False,
    full_hash: Annotated[bool, typer.Option("--full-hash", help="sha256 of whole files as asset IDs (slower).")] = False,
    as_json: JsonOption = False,
) -> None:
    """Index files and folders: transcripts and captions, searchable with `tapesift search`."""
```
The flow. Module-level imports are typer, json, math, pathlib, `tapesift.cli` and `tapesift.config` only. `tapesift.runner.run`, `tapesift.runner.report`, `tapesift.pipeline.index` and rich are imported inside the function, and the pipeline module is used through its attributes (`pi.load`, `pi.open_store`, `pi.resolve_config`), so tests can monkeypatch them. Before step 1 it calls `install_interrupt_handlers()` (restored in `finally`). The whole body is wrapped so that an `Interrupted` (or `KeyboardInterrupt`) escaping before the run prints `interrupted` to stderr and exits `128 + signum` (card 10).
1. If `max_media_hours is not None and not (math.isfinite(max_media_hours) and max_media_hours > 0)`, raise `typer.BadParameter("must be a positive number of hours of media", param_hint="--max-media-hours")`. That exits 2.
2. `cfg = load_config(config, profile=profile, out_dir=out)`. A `ConfigError` prints `error: <message>` to stderr and exits 2.
3. `cfg = pi.resolve_config(cfg)`. A `ModelLoadError` prints `error: <message>` and exits 3.
4. Logging. If the `tapesift` logger has no handlers, add `RichHandler(console=err, show_path=False, markup=False)` at INFO, where `err = Console(stderr=True)`.
5. The progress bar is shown only when `err.is_terminal and not as_json`: `Progress(TextColumn("{task.description}", markup=False), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=err, transient=False)`. The callback calls `update(task, total=total, completed=done, description=current)`. File names are never parsed as rich markup, so `[red].mp4` prints literally.
6. `summary = run_index(paths, cfg, load=pi.load, open_store=None if dry_run else pi.open_store, full_hash=full_hash, max_media_hours=max_media_hours, progress=...)`.
   - `OutDirError` prints `error: <message>` and exits 2.
   - `ModelLoadError` prints `error: <message>` and exits 3.
   - `StoreError` (E6, `tapesift.store.lance`, imported inside the function only when not a dry run, because it loads lancedb) prints `error: <message>` and exits 2.
   - `OSError` prints `error: cannot use {cfg.out_dir}: {e.strerror or e}` and exits 2.
7. Output. If `summary.interrupted`, first call `exit_on_next_signal(summary.interrupted_by)`. With `--json`, stdout gets `json.dumps(to_dict(summary), ensure_ascii=False, indent=2)` and nothing else. Otherwise stderr gets `render(summary)`.
8. Exit `128 + summary.interrupted_by` if interrupted (130 SIGINT, 143 SIGTERM, 129 SIGHUP; literals, since `ExitCode` isn't edited), else `ExitCode(summary.exit_code)`.

### docs/spec.md edits
1. **Line 212.** After `**3** environment problem (missing GPU, missing model).`, append ` \`tapesift index\` also exits **130**, **143** or **129** when stopped by SIGINT (Ctrl-C), SIGTERM or SIGHUP; rerunning resumes.` (card 10).
2. **Line 217** (after M1's edit 7) becomes exactly (cards 7 and 9):
   ```
   | `tapesift index PATH... [--config FILE] [--profile] [--out DIR] [--max-media-hours H] [--dry-run] [--full-hash]` | Indexes files or folders; resumes by content hash; `--max-media-hours` stops starting new files after H hours of media; `--dry-run` probes and prints the plan (files, media hours, skip and resume counts) and writes nothing; `--workers N` arrives with S1 (v0.3) | v0.1 |
   ```
3. **Line 299** (card 11): the case cell `Not a media file or unopenable (e.g. \`.srt\`, \`.DS_Store\` in a folder)` becomes `Not a media file or unopenable (e.g. \`.srt\`, \`notes.txt\` in a folder; hidden entries such as \`.DS_Store\` are skipped and logged by \`tapesift index\`)`. The code column is unchanged, so `test_fixtures.py` still parses it.

## Acceptance
**Baseline, before phase 1.** On its base commit, the builder measures and states in the PR:
- `uv run pytest -q -m "not gpu and not model"` as `B passed, D deselected`;
- the wall time of `make check` (median of 3).

Every count below is relative to `B` and `D`.

**Test support (`tests/runner_setups.py`).** Module-level, so a spawned worker can import it by name.
- `quick(cfg) -> Analyze`. It does no decoding. When the env var `TAPESIFT_TEST_SPY` is set, the load step appends `f"pid:{os.getpid()}\n"` to that file. The returned callable runs `on_stage("asr")`, appends `asset.path.name + "\n"` to the spy file, and returns `AssetRecord(asset, (), (), (), Provenance(__version__, None, None, None))`.
  - The env var `TAPESIFT_TEST_FAULTS` (`"name:fault,name:fault"`) injects faults by file name:
    - `boom`: raise `RuntimeError("boom")`;
    - `stuck`: `time.sleep(300)`, no beats;
    - `beating`: 3 s of `beat()` every 0.2 s, then return;
    - `crash`: `os._exit(3)`;
    - `killparent`: `os.kill(os.getppid(), signal.SIGKILL)`, then `time.sleep(300)`;
    - `slow`: `time.sleep(300)`;
    - `log`: `logging.getLogger("tapesift.test").warning("hello", extra={"asset_id": asset.id, "stage": "asr"})`;
    - `print`: `print("noise")`.
  - Faults are read in the worker. Tests set them with `monkeypatch.setenv` before `run_index`; spawned children inherit the environment.
- `broken(cfg)`: raises `ModelLoadError("fake: no model")`.
- `dies(cfg)`: `os._exit(3)`.
- `slowload(cfg)`: `time.sleep(300)`.
- `fake_pipeline(cfg) -> Analyze` (card 1, phase 2): `functools.partial(index_asset, backends=Backends(PyAVDecoder(), FakeVAD(), FakeASR(), FakeVLM() if cfg.vlm.backend == "transformers" else None), cfg=cfg)`, plus the same spy line.
- `SpyStore(MemoryStore)`: built with `FakeEmbedder()`. It records `upserts: list[str]` and `deletes: list[str]` (asset IDs), and raises `fail_on[path.name]` from `upsert` when set. It runs in the parent only.
- `SIX`: clean.mp4, speech.mp4, vfr.mp4, no_audio.mp4, short_clip.mp4 and rotated_270.mp4. They have six distinct IDs. Tests copy them into `tmp_path / "in"` as a.mp4 to f.mp4, in that order, unless a row says otherwise.
- **Driver scripts.** Tests that need a separate process write a script file to `tmp_path` whose body sits under `if __name__ == "__main__":`, and run it with `subprocess.run([sys.executable, str(script), ...], timeout=120)` or `Popen`. The guard keeps spawn's re-import of the main module from re-running it.

`...u` means `uv run pytest tests/unit/test_runner_plan.py -q`. `...p` means `tests/unit/test_pipeline_index.py`, `...s` means `tests/smoke/test_runner_isolation.py`, and `...f` means `tests/smoke/test_index_fixtures.py`.

### `tests/unit/test_runner_plan.py`: 44 tests (no worker)
| Test | Count | Asserts |
| --- | --- | --- |
| `test_walk_order` | 1 | Tree `in/b/z.mp4`, `in/a/y.mp4`, `in/B.mp4`, `in/é.mp4`, `in/a.mp4`. `walk([in])` equals exactly `[in/B.mp4, in/a.mp4, in/é.mp4, in/a/y.mp4, in/b/z.mp4]` (files before subfolders; observed). `walk([in/b, in/a])` gives `[in/b/z.mp4, in/a/y.mp4]` |
| `test_walk_skips_hidden_and_logs` | 1 | `.DS_Store`, `._a.mp4` and `.cache/x.mp4` are absent from `walk([in])`. caplog has exactly 3 INFO lines `skipping hidden <path>`; `.cache` is logged once and `x.mp4` not at all. `walk([in/.DS_Store])` returns it |
| `test_walk_absolute_and_deduped` | 1 | With `monkeypatch.chdir(tmp_path)`: `walk([Path("in"), Path("in/a.mp4"), Path("./in")])` lists each file once, each `is_absolute()`. A symlinked folder passed as an argument keeps the link's path |
| `test_walk_does_not_enter_symlinked_folders` | 1 | `in/link -> ../other` (a folder) is not entered. `in/l.mp4 -> ../other/x.mp4` is listed |
| `test_walk_reports_unlistable_folder` | 1 | `tapesift.runner.run.os.walk` is monkeypatched to a generator that calls `onerror(PermissionError(13, "Permission denied", str(in / "locked")))` and then yields `(str(in), [], ["a.mp4"])`. Result: `[FileResult(str(in/"locked"), "failed", None, None, UNREADABLE, None, "cannot list folder: Permission denied"), in/a.mp4]`. No chmod, so it also holds under root |
| `test_walk_rejects_undecodable_name` | 1 | `walk([Path("/x/bad\udcff.mp4")])` gives one `FileResult` with path `"/x/bad\\xff.mp4"`, UNREADABLE, detail `"file name is not valid UTF-8"` |
| `test_read_marker[<case>]` | 3 | **valid**: an exact `Marker` round-trips. **unparsable**: `b"{"` gives None and one WARNING. **wrong_shape**: `attempts: "2"` gives None and one WARNING |
| `test_retry_allowed[<case>]` | 4 | None gives True; `attempts 1` on the same version gives True; `attempts 2` on the same version gives False; `attempts 2` on `"0.0.1"` gives True |
| `test_next_attempts[<case>]` | 3 | None gives 1; 1 on the same version gives 2; 2 on another version gives 1 |
| `test_small_json_write[<case>]` | 2 | **ok**: the file parses, and the folder holds only it (no `.tapesift-*.tmp`). **replace_fails**: with `os.replace` patched to raise `OSError`, the old bytes are kept, no temp file is left, and the error propagates |
| `test_limits[<case>]` | 5 | `probe_deadline(0, full=False) == 120.0`; `probe_deadline(100 * 2**20, full=True) == 130.0`; `index_deadline(None) == 43200.0`; `index_deadline(10.0) == 650.0`; `index_deadline(10800.0) == 43200.0` (a 3 h file gets 12 h, not 30 h) |
| `test_open_out_dir[<case>]` | 8 | **fresh**: creates `assets/`, `failed/`, `.lock`, and `index.json == {"layout": 1, "id_mode": "tsid1"}`. **same_mode**: OK, and `assets/.tapesift-123.tmp` and `failed/.tapesift-9.tmp` are removed. **other_mode**: `OutDirError` with exactly `f"{out} is a tsid1 index; this run uses sha256 IDs. Rerun without --full-hash, or use another --out."`. **dry_missing**: `create=False` on a missing folder creates nothing. **empty_index_fresh**: an empty `index.json` with no asset or marker files is rewritten as tsid1. **unknown_with_assets**: `{"layout": 1, "id_mode": "tsid2"}` plus one asset file gives `OutDirError` ending `"use another --out."`. **other_layout**: `{"layout": 2, "id_mode": "tsid1"}` plus one asset file gives the same error. **busy**: while the test holds `flock` on `out/.lock`, `OutDirError(f"{out} is in use by another tapesift index run")` |
| `test_asset_file_name` | 1 | `asset_file_name("tsid1:" + "ab" * 32) == "tsid1_" + "ab" * 32 + ".json"`, and the same for `sha256:`. Each result fullmatches `ASSET_FILE_RE` |
| `test_scan_assets` | 1 | Two valid minimal docs (`{"asset": {"id": X, "path": P}}`, saved under `asset_file_name(X)`) are mapped by the ID inside the JSON. A truncated JSON, a doc whose name doesn't match its ID, and `.x.json` are ignored. Exactly 2 WARNINGs are logged (truncated, mismatch). A missing folder gives `{}` |
| `test_exit_code[<case>]` | 5 | Statuses only indexed gives 0; one failed gives 1; one failed_before gives 1; only duplicate and skipped gives 0; only deferred gives 0 |
| `test_to_dict_exact` | 1 | A hand-built `Summary` with one file of each of the 7 statuses gives exactly the literal dict pinned in the test: `"version": 1` first, key order, `counts` with all 7 keys, `media_hours` rounded to 4 places, `code` as a string or None, no `duration_s` |
| `test_render_exact[<case>]` | 3 | **normal** (including the failed-before section and its retry line), **dry_run**, and **interrupted_and_deferred**: each equals the pinned text, built from the format strings under Interfaces |
| `test_second_signal_exits_immediately` | 1 | With `tapesift.runner.run.os._exit` patched to a recorder: `exit_on_next_signal(signal.SIGTERM)`, then `signal.raise_signal(signal.SIGINT)`, records `[143]`. The previous handlers are restored in `finally` |
| `test_cli_import_loads_no_backends` | 1 | `subprocess.run([sys.executable, "-c", "import sys, tapesift.cli; print(sorted({...} & set(sys.modules)))"], timeout=60)`, with the R6 set plus `av` and `rich.progress`, prints `[]` |

Count: 6 (walk) + 3 + 4 + 3 + 2 + 5 + 8 + 1 + 1 + 5 + 1 + 3 + 1 + 1 = **44**.

### `tests/unit/test_pipeline_index.py`: 16 tests
Inputs are built in the module: a `_StubDecoder` (it satisfies `Decoder`) that yields given chunks and frames, or raises a given `DecodeError`; M1's contract inputs `BURSTS` and `ZEROS` at `start_s=0.0`; two 64x48 grey frames at `t_s` 0.0 and 1.0; the asset is `AssetInfo("tsid1:" + "0" * 64, Path("/x/a.mp4"), 2.0, VideoInfo(0, "h264", 64, 48, 25.0, False, 0), (AudioStreamInfo(1, "aac", None, True),), ())`. `beat` is a counter.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_resolve_auto_with_vision` | 1 | `vlm.backend == "transformers"`; no WARNING |
| `test_resolve_auto_without_vision` | 1 | `"none"`; exactly one WARNING, with message `captions off: install "tapesift[vision]"` |
| `test_resolve_explicit_transformers_without_vision` | 1 | `ModelLoadError` whose message contains `tapesift[vision]` |
| `test_resolve_none_logs_info` | 1 | One INFO line: `captions off (vlm.backend = "none")` |
| `test_resolve_fills_profile` | 1 | `profile=None` with `Probes(which=lambda _: None)` gives `Profile.CPU` |
| `test_resolve_keeps_explicit_profile` | 1 | `profile="gpu"` stays `gpu`, and the probes are never called (their `run` raises) |
| `test_both_stages_run` | 1 | `BURSTS` and frames give at least 1 utterance and 2 captions; provenance is `("fake:asr@"+Z, "fake:vlm@"+Z, "caption_v1")` |
| `test_audio_stage_error_degrades` | 1 | `iter_audio` raises `DecodeError(UNREADABLE, "x")`: utterances `()`, `asr is None`, the warning is on the record, and 2 captions remain |
| `test_caption_stage_error_degrades` | 1 | `iter_frames` raises `DecodeError(UNSUPPORTED_CODEC, "y")`: captions `()`, `vlm` and `prompt` None, the warning is on the record, and the utterances remain |
| `test_no_audio_means_no_asr` | 1 | `audio=()`: `asr is None`; FakeASR `calls == []` |
| `test_low_speech_means_no_asr_id` | 1 | `ZEROS`: `LOW_SPEECH` is on the record and `asr is None` |
| `test_captions_off` | 1 | `vlm=None`: captions `()`, `vlm` and `prompt` None, and no code beyond the audio stage's |
| `test_unexpected_error_propagates` | 1 | A FakeASR subclass raising `RuntimeError("x")`: `index_asset` raises it, and `on_stage` saw `["asr"]` |
| `test_stage_order` | 1 | `on_stage` calls are `["asr", "vlm", "record"]` |
| `test_decoder_items_beat` | 1 | With 1 audio chunk and 2 frames, `beat` is called at least 3 times |
| `test_pipeline_import_is_light` | 1 | A subprocess (`timeout=60`) importing `tapesift.pipeline.index` prints `[]` for `torch`, `transformers`, `ctranslate2`, `faster_whisper`, `lancedb`, `pyarrow`, `onnxruntime`, `tokenizers` and `huggingface_hub` |

### `tests/smoke/test_runner_isolation.py`: 41 tests (real worker processes and real `probe`; `load=quick` unless a row says otherwise; `open_store=lambda c: spy`)
| Test | Count | Asserts |
| --- | --- | --- |
| `test_indexes_each_file_once` | 1 | SIX: 6 indexed, in walk order. `assets/` holds exactly 6 files, each named `asset_file_name(<its asset.id>)` with no `:` in any name, and each `asset.path == str(in / name)` is absolute. `index.json == {"layout": 1, "id_mode": "tsid1"}`. `spy.upserts` lists the 6 IDs in order. `progress` calls are `[(0, 6, "a.mp4"), ..., (5, 6, "f.mp4"), (6, 6, "")]`. No `.tapesift-*.tmp` under `out` |
| `test_rerun_processes_nothing` | 1 | Second run: 6 skipped, no new file-name lines in the spy file (0 analyses), and 0 upserts. Done-when: "a rerun skips finished files" |
| `test_bad_file_fails_alone` | 1 | SIX plus `not_media.txt` copied in as `c0.txt`. It alone fails: `UNREADABLE`, detail `"InvalidDataError: Invalid data found when processing input"`, no marker. The 6 others are indexed. `exit_code == 1` |
| `test_unexpected_exception_fails_asset` | 1 | Faults `b.mp4:boom`: b fails with stage `asr` and detail `"RuntimeError: boom"`. Its marker is exactly `{"path": str(in/b.mp4), "stage": "asr", "exception": "RuntimeError", "error": "RuntimeError: boom", "attempts": 1, "tapesift": __version__}`. No b JSON and no upsert for b; the other 5 are indexed |
| `test_retry_cap_two_per_version` | 1 | Run 2: b is retried, attempts 2. Run 3: failed_before with detail `f"failed before (2 attempts on {__version__}); not retried"` and no analysis of b. Then the marker's `tapesift` is set to `"0.0.1"`; run 4 retries b and attempts becomes 1. Exit 1 on every run |
| `test_success_deletes_marker` | 1 | After a `boom` run, a run without faults indexes b, and b's marker file is gone |
| `test_marker_write_failure_does_not_stop_batch` | 1 | Faults `b.mp4:boom`, with `tapesift.runner.run._write_small_json` patched to raise `OSError("disk full")` for paths under `failed/`: b fails, one ERROR `cannot write failed marker for ...` is logged, and c to f are indexed |
| `test_store_error_fails_asset` | 1 | `spy.fail_on["c.mp4"] = RuntimeError("db")`: c fails with stage `store`, a marker is written, there is no c JSON, and the rest are indexed |
| `test_getsize_error_fails_file` | 1 | `full_hash=True`, with `tapesift.runner.run.os.path.getsize` patched to raise `FileNotFoundError(2, "No such file or directory")` for c: c fails `UNREADABLE` with detail `"No such file or directory"`, and the rest are indexed |
| `test_wall_clock_limit_kills_stuck_worker` | 1 | (#36) Faults `c.mp4:stuck`, `Limits(index_min_s=1.0, index_per_media_s=0.0)`. c fails with detail `"WorkerTimeout: timed out after 1 s"` and stage `asr`; marker `exception == "WorkerTimeout"`. d to f are indexed by a new worker. The run ends in under 120 s, far below the 300 s sleep, which proves the kill |
| `test_no_progress_limit_kills` | 1 | Faults `c.mp4:stuck`, `Limits(stall_s=1.0)` (default deadline, 600 s or more): c fails with detail `"WorkerTimeout: no progress for 1 s"`, and the run ends in under 120 s |
| `test_beats_keep_slow_file_alive` | 1 | Faults `c.mp4:beating`, `Limits(stall_s=1.0)`: c is indexed |
| `test_probe_timeout_is_unreadable` | 1 | One file, `Limits(probe_s=1e-4)`: failed, `UNREADABLE`, detail `"timed out after 0.0001 s"`, stage `probe`, no marker |
| `test_worker_crash_fails_asset` | 1 | Faults `b.mp4:crash`: detail `"WorkerCrashed: worker exited with code 3"`; marker `exception == "WorkerCrashed"`; c to f are indexed |
| `test_worker_dies_while_loading` | 1 | `load=dies`: `ModelLoadError("worker exited with code 3 while loading models")`; no JSON and no marker |
| `test_model_load_wait_is_bounded` | 1 | `load=slowload`, `Limits(load_s=1.0)`: `ModelLoadError("models did not load within 1 s")` in under 60 s |
| `test_load_error_is_model_load_error` | 1 | `load=broken`: `run_index` raises `ModelLoadError("fake: no model")`; no JSON and no marker |
| `test_hard_kill_then_rerun_resumes_from_k` | 1 | Done-when. A driver script runs `run_index` on SIX with faults `c.mp4:killparent`; its return code is -9. `assets/` holds exactly the a and b JSONs. Within 10 s, the worker pid from the spy file's `pid:` line no longer exists (`os.kill(pid, 0)` raises `ProcessLookupError`): the watchdog works. Then an in-process rerun with no faults: the new file-name lines are exactly `c.mp4`, `d.mp4`, `e.mp4` and `f.mp4`; 6 JSONs exist; a and b are skipped |
| `test_signal_stops_and_resumes[<sig>]` | 3 | Parametrized: SIGINT gives 130, SIGTERM 143, SIGHUP 129. A driver script runs the CLI (`tapesift.cli.main`, with `pi.load = quick` and `pi.open_store` building a `MemoryStore`) on SIX with faults `b.mp4:slow`. Once a's JSON exists, the test sends the signal. The process exits with that code within 10 s; stderr contains `f"interrupted by {name} after 1 of 6 files; rerun to resume"`; exactly 1 JSON exists; there is no marker for b and no temp file. A rerun indexes b to f |
| `test_json_stdout_stays_clean` | 1 | The same driver with `--json` and faults `a.mp4:print`: stdout parses with `json.loads`, and stderr contains `noise` |
| `test_signal_during_write_is_deferred` | 1 | In-process: `SpyStore` sends `os.kill(os.getpid(), signal.SIGINT)` to itself from inside `upsert` for b. `upsert` finishes and b's JSON is written; then the interrupt lands, and the summary has a and b indexed with `interrupted_by == SIGINT` |
| `test_keyboard_interrupt_returns_partial_summary` | 1 | In-process: `spy.fail_on["b.mp4"] = KeyboardInterrupt()`. `run_index` returns `interrupted_by == signal.SIGINT` with `files == (a indexed,)` and `total == 6`. `multiprocessing.active_children() == []` |
| `test_duplicate_confirmed_by_full_hash` | 1 | (#11) clean.mp4 and clean_copy.mp4 only: clean is indexed; clean_copy is duplicate with `code == DUPLICATE` and detail `f"same content as {in/'clean.mp4'}"`; there is 1 JSON |
| `test_duplicate_stays_duplicate_on_rerun` | 1 | Rerun: clean skipped, clean_copy duplicate, 0 analyses |
| `test_same_file_is_never_its_own_duplicate` | 1 | Index `in/a.mp4`, then rerun with `in/a.mp4` and `in/l.mp4 -> a.mp4` (plus, on a case-insensitive file system, `in/A.mp4`): l is skipped with detail `f"same file as {in/'a.mp4'}"`, never a duplicate, and nothing is hashed (no `hash` stage in the logs) |
| `test_tsid1_collision_indexes_both` | 1 | (#11) Two WAVs written in the test with stdlib `wave` and numpy: 16 kHz mono s16, `17 * 2**20` data bytes each; identical first and last 8 MiB of the file; the middle 1 MiB is seeded noise, seed 1 and seed 2. The test first asserts `asset_id(p1) == asset_id(p2)` and that the full IDs differ. After the run: p1 is indexed as the tsid1 ID; p2 is indexed with `asset_id == asset_id(p2, full=True)`; 2 JSONs; one WARNING starting `"tsid1 collision: "` that names both paths. A rerun skips both, with 0 analyses |
| `test_copy_of_collision_resolved_file_is_duplicate` | 1 | p1, p2 as above, and p3 a byte copy of p2: p3 is duplicate with detail `f"same content as {p2}"`; p2's JSON is unchanged (bytes and mtime) |
| `test_collision_survivor_skipped_after_original_deleted` | 1 | After indexing p1 and p2, delete p1 and rerun: p2 is skipped (not "already indexed as p1"), with 0 analyses |
| `test_moved_file_is_skipped` | 1 | (card 12) Index `in/a.mp4`, move it to `in/sub/a.mp4`, and rerun: skipped, detail `f"already indexed as {old}"`, 0 analyses |
| `test_changed_file_replaces_old_record` | 1 | Index `in/x.mp4` (clean bytes), overwrite it with speech.mp4's bytes, and rerun: indexed with the new ID; `spy.deletes == [old id]`; the old ID's asset file is gone and the new one exists |
| `test_store_rows_without_json_reindex` | 1 | (E5 coordination) After a full run, delete c's asset file. The store still has c's rows, and the rerun re-indexes exactly c: new spy line `c.mp4`, upsert again, JSON present |
| `test_corrupt_json_is_reindexed` | 1 | Truncate d's asset file to its first 10 bytes. The rerun logs `ignoring unreadable <name>: JSONDecodeError`, re-indexes d, and the JSON parses again |
| `test_id_mode_mismatch_refused` | 1 | After a tsid1 run, `run_index(..., full_hash=True)` raises `OutDirError` with the exact message; no file under `out` changed (names and mtimes) |
| `test_full_hash_mode` | 1 | A fresh out with clean and clean_copy and `full_hash=True`: IDs start `sha256:`; `index.json` is `sha256`; clean_copy is duplicate |
| `test_max_media_hours_defers_rest` | 1 | (card 9) `max_media_hours=0.001` (3.6 s): a (clean, 5 s) is indexed, b to f are deferred with `asset_id None` and unprobed, and `exit_code == 0`. A rerun without the budget skips a and indexes b to f |
| `test_dry_run_writes_nothing` | 1 | A fresh `out`: `open_store=None` gives 6 pending; `out` doesn't exist afterwards; no `pid:` line (load never ran). After a real run of a and b only, a dry run of SIX shows a and b skipped and c to f pending |
| `test_dry_run_finds_duplicates` | 1 | A fresh `out` with clean and clean_copy, dry run: clean pending, clean_copy duplicate, and `media_hours() == 5.0 / 3600` (the duplicate isn't counted) |
| `test_unicode_paths_round_trip` | 1 | `réunion 01.mp4` copied to `in/dossier é/réunion 01.mp4`, plus `in/[red]é 🎬.mp4` (a copy of speech): both indexed; each JSON's `asset.path` equals `str(path)` exactly; `to_dict` serialized with `ensure_ascii=False` contains both names unescaped |
| `test_worker_logs_reach_parent` | 1 | Faults `a.mp4:log`: caplog has a WARNING `hello` from `tapesift.test` with `asset_id == a's id` and `stage == "asr"` |

Count: **41** (the signal test counts 3).

### `tests/smoke/test_index_fixtures.py`: 15 tests (CLI; real `probe`, `PyAVDecoder`, E3, E4 and E5; fakes for every model)
A module-scoped fixture monkeypatches `tapesift.pipeline.index.load = fake_pipeline`, `open_store = lambda c: MemoryStore(FakeEmbedder())` and `vision_available = lambda: True`. It runs `CliRunner().invoke(app, ["index", str(FIXTURES), "--out", str(out), "--json"])` once and parses stdout. `NAME(r)` is `Path(r["path"]).name`.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_only_unreadable_files_fail` | 1 | Done-when ("the corrupt fixture fails alone"). Exit 1. `total == 26`. The `failed` names are exactly `{"not_media.txt", "manifest.json"}`, both `code == "UNREADABLE"`; not_media.txt's detail is `"InvalidDataError: Invalid data found when processing input"`. manifest.json's detail is pinned by the builder from the observed run (verify, with evidence in the PR). `failed_before == 0`. The `duplicate` names are exactly `{"clean_copy.mp4"}` with detail `f"same content as {FIXTURES.absolute() / 'clean.mp4'}"`. `indexed == 23` and `counts` are exact. truncated.mp4 and unknown_codec.mov are indexed, not failed |
| `test_every_json_validates` | 1 | Each of the 23 `assets/*.json` passes `Draft202012Validator` with E5's `asset-1.0.schema.json` (via `importlib.resources`) |
| `test_manifest_codes_reach_output` | 1 | For each manifest fixture: `set(codes) - {"CROPPED", "MEDIA_TEXT"}` (C3; FakeVLM reads no text) is a subset of the JSON's warning codes plus the summary `code`. So silence.mp4 and music.m4a show `LOW_SPEECH`, truncated.mp4 `PARTIAL_DECODE`, clean_copy.mp4 `DUPLICATE` and not_media.txt `UNREADABLE` |
| `test_rerun_indexes_nothing` | 1 | A second invoke: exit 1; counts `skipped 23, duplicate 1, failed 2`; no new spy lines |
| `test_human_summary_on_stderr` | 1 | Without `--json`, on a copy of {clean, clean_copy, not_media}: stdout is empty; stderr contains the headline `indexed 1, skipped 0, duplicate 1, failed 1, failed before 0, deferred 0 (3 files,` and the lines `failed:` and `duplicate:` |
| `test_id_mode_mismatch_exits_2` | 1 | A tsid1 index, then `--full-hash` on the same `--out`: exit 2, and stderr is `error: ` plus the exact `OutDirError` message |
| `test_bad_config_exits_2` | 1 | `--config` with `colour = 1`: exit 2; stderr contains `colour: Extra inputs are not permitted` |
| `test_missing_path_exits_2` | 1 | `index /nonexistent`: exit 2 |
| `test_max_media_hours_must_be_positive` | 1 | `--max-media-hours 0`: exit 2; stderr names `--max-media-hours` |
| `test_store_error_exits_2` | 1 | `pi.open_store` raises `StoreError("x: not a tapesift store")`: exit 2; stderr is `error: x: not a tapesift store` (E6 card 6) |
| `test_model_load_error_exits_3` | 1 | `pi.load = broken`: exit 3; stderr is `error: fake: no model` |
| `test_config_out_dir_relative_to_config_file` | 1 | `conf/t.toml` with `out_dir = "idx"`, from another cwd: `conf/idx/index.json` exists (M1 card 4) |
| `test_dry_run_json` | 1 | `--dry-run --json` on {clean, not_media}: `dry_run` true; `counts.pending == 1`; `counts.failed == 1`; `out` not created; exit 1 |
| `test_python_dash_m_spawns_cleanly` | 1 | `subprocess.run([sys.executable, "-m", "tapesift", "index", str(FIXTURES / "clean.mp4"), "--out", str(tmp), "--dry-run", "--json"], timeout=120)`: exit 0, and stdout parses with `counts.pending == 1`. Without the `__main__.py` guard the worker re-runs the CLI and this fails |
| `test_progress_bar_on_a_terminal` | 1 | With env `TTY_COMPATIBLE=1` and `TTY_INTERACTIVE=1` (rich 15) and no `--json`, on a 2-file folder: stderr contains `2/2`. The builder may adjust the env mechanism with evidence; the assertion stays |

### `tests/smoke/test_index_models.py`: 2 tests, `@pytest.mark.model` (the `models` CI job only, Q4; never on the laptop, ADR 0008)
A config file sets `profile = "cpu"`, `[asr] model = "tiny"` and `[sampling] fixed_fps = 0.005`, so long_3h.mp4 gives 54 frames. There are no patches, so the real `load` and `open_store` run.
- `test_models_index_all_fixtures`: exit 1. The same failed, duplicate and indexed sets as `test_only_unreadable_files_fail`, and all 23 JSONs validate. speech.mp4's `provenance.asr == ASR_MODELS["tiny"].id`, and when `vision_available()`, `provenance.vlm == VLM_MODELS["smolvlm2-256m"].id`. This is spec 333's "CI indexes all fixtures on CPU".
- `test_models_rerun_skips`: counts `skipped 23, duplicate 1, failed 2`.

### Commands
| Command | Expected |
| --- | --- |
| Phase 1 checkpoint (card 1), before phase 2 starts | `...u` gives `44 passed`; `...s` gives `37 passed`; `uv run pytest -q -m "not gpu and not model"` gives `B + 81 passed`; pyright and ruff clean |
| `...u` | `44 passed` |
| `...p` | `16 passed` |
| `...s` | `41 passed` |
| `...f` | `15 passed` |
| `uv run pytest tests/smoke/test_index_models.py -q --co -m model` | `2 tests collected` (they run only in the `models` job) |
| `uv run pytest -q -m "not gpu and not model"` | `B + 116 passed`, `D + 2 deselected`, with no `failed`, `error`, `skipped` or `xfailed` |
| `uv run pytest tests/unit/test_cli.py -q` | unchanged count, all pass (the `__main__` guard) |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff format --check .` and `uv run ruff check .` | clean |
| `grep -c 'arrives with S1 (v0.3)' docs/spec.md` | `1` |
| `grep -c -- '\[--workers N\]' docs/spec.md` | `0` |
| `grep -c 'also exits \*\*130\*\*, \*\*143\*\* or \*\*129\*\*' docs/spec.md` | `1` |
| `grep -c 'skipped and logged by `tapesift index`' docs/spec.md` | `1` |
| `uv run pytest tests/unit/test_fixtures.py -q` | all pass (line 299's code column unchanged) |
| `grep -rn 'json.dump' src/tapesift/runner` | only in `_write_small_json` (asset JSON is E5's `write_json`) |
| `grep -c 'get_context("spawn")' src/tapesift/runner/run.py` | `1` |
| `git diff --numstat main -- CHANGELOG.md` | `1	0	CHANGELOG.md` |
| `git diff --name-only main...HEAD` | exactly these 16 paths: `CHANGELOG.md`, `docs/spec.md`, `src/tapesift/__main__.py`, `src/tapesift/cli/__init__.py`, `src/tapesift/cli/index.py`, `src/tapesift/pipeline/__init__.py`, `src/tapesift/pipeline/index.py`, `src/tapesift/runner/__init__.py`, `src/tapesift/runner/report.py`, `src/tapesift/runner/run.py`, `tests/runner_setups.py`, `tests/smoke/test_index_fixtures.py`, `tests/smoke/test_index_models.py`, `tests/smoke/test_runner_isolation.py`, `tests/unit/test_pipeline_index.py`, `tests/unit/test_runner_plan.py` |
| `make check` | exits 0. The PR reports its wall time (median of 3) next to the baseline (Risks) |

## Out of scope
- `--workers` and any parallel or pipelined scheduling (S1, v0.3). The SQLite job store (S2). `tapesift report` (S4, v0.3, which reads `failed/`). `--log-json`. A cost line in `--dry-run` (C7).
- Config keys for the limits in card 3 (a card, if users need them). Aborting after N abandoned workers (see Risks).
- Rewriting the stored path of a moved file (card 12), and pruning stale markers of changed files.
- Manifest-file inputs (spec 36, v1.0); JSONL, SRT and CSV export (v0.3); Unicode normalization of paths; Windows-native paths (spec non-goal).
- Re-validating existing JSON against the schema at resume time (`jsonschema` is dev-only).
- A `--redact-paths` export that strips or relativizes `asset.path` before sharing (card 5; future), and the README privacy note (E9).
- A `last-run.json` or any saved summary file (card 6: the summary is stderr or `--json` only).
- Beats from inside a single backend call. A long ASR call on one 600 s chunk shows no progress until it returns, which is why `stall_s` is 30 min.

## Risks
- **E6's `StoreError` is a draft name** (29-search card 6). If it changes before phase 2, `cli/index.py` step 6 and `test_store_error_exits_2` follow it.
- **A read stuck in the kernel can't always be killed.** SIGKILL doesn't reap a process in uninterruptible sleep (a hard-mounted dead NFS). The runner abandons such a worker after `KILL_JOIN_S`, and the worker keeps its memory (models included) until the mount recovers. Many stuck files on one dead mount can pile up abandoned workers. `ponytail:` comment, ceiling: one abandoned worker per stuck file; upgrade path: abort the run after 3 abandoned workers, by card.
- **The parent touches input paths:** `os.walk`, `getsize`, `exists` and `samefile`. A mount that hangs on `readdir` or `stat` hangs the parent. The upgrade path is moving those calls into the worker.
- **Limits may kill legitimate work** (card 3): a CPU slower than about 4x realtime on a 3 h file hits the 12 h ceiling; one backend call longer than 30 min trips the no-progress limit. The marker cap then stops the retries after 2. The fix is a config key, by card.
- **`--max-media-hours` under S1** (card 9). Today one file is in flight, so the budget overshoots by at most one file. When S1 pipelines files, every file already in flight when the budget is reached finishes and counts toward the hours, so the overshoot is the in-flight set. S1's spec must keep that rule and state it.
- **Blocked signals during writes** (card 10). If a store write hangs (a dead disk under `out_dir`), Ctrl-C, SIGTERM and SIGHUP stay pending until it returns. SIGKILL still works. The blocked sections are store writes and small file writes only, never a worker wait.
- **Spawn start-up.** Each worker start imports numpy, PyAV and the models (seconds on CPU), once per run and again after each kill or crash. A Ctrl-C that lands during the few milliseconds of `start()` with SIGINT ignored is lost; the next one works.
- **The start-up scan reads every asset JSON.** `ponytail:` comment, ceiling: O(total JSON bytes) per run, for example about 30 s for 1,000 three-hour assets; upgrade path: S2's job store.
- **Duplicates are re-hashed on every rerun** (two full reads each), and so are collision-resolved files. `ponytail:` comment; S2 caches full IDs.
- **`flock` on network file systems** may be advisory or a no-op (some NFS setups). Two runs on one NFS `--out` may then both proceed. Documented; not detected.
- **rich must be declared by M1** (card 13). If M1 merges without it, stop and raise a card; don't edit `pyproject.toml` here.
- **Timing-based tests** (stuck, stall, SIGINT, hard kill, slow load) sleep 300 s in the fault and assert endings under 60-120 s, so a cold spawn on a slow CI runner can't flake them. Never shorten a bound to make a test pass.
- **`filterwarnings = error`.** An unclosed `Connection`, `Process` or file is a ResourceWarning and fails the suite. Close everything, in tests too.
- **`make check` time.** About 50 worker spawns (about 1 s each) and one full fixture pass (long_3h.mp4's 10,800 frames through FakeVLM) add roughly 1-2 minutes. The builder measures the baseline before phase 1. If `make check` goes over 3 minutes (P0.3), report both numbers and raise a card (for example, mark the fixture pass `slow`). Never delete tests.
- **Stage behaviour assumed from M1 docstrings:** `LOW_SPEECH` arrives through `warn`; `transcribe_asset` returns `[]` with no audio; `caption_asset` returns `[]` with no video. If E3 or E4 differ, `test_pipeline_index.py` fails. Stop and raise a card; don't change the assertions.
- **Merge order.**
  - `CHANGELOG.md` conflicts with E3, E4, E5, E6 and E8 (keep every line).
  - `docs/spec.md` conflicts with M1 (line 217 builds on M1's edit 7) and with E5 (the output block, a different hunk). Rebase after M1, keep both.
  - `src/tapesift/cli/__init__.py` conflicts with E6 if it also registers `search`; keep both registrations.

## T1 calls (list them in the PR)
1. Stage names in markers and summaries: `probe`, `hash`, `worker`, `asr`, `vlm`, `record`, `store`, `write`.
2. Exact detail strings (timeout, no progress, crash, failed before, duplicate, same file, moved, cannot list folder, name not UTF-8).
3. A malformed marker counts as absent, with a WARNING. A fresh-looking `index.json` (empty or unparsable, with no asset or marker files) is rewritten.
4. Failure to prepare `out_dir` exits 2 (a bad `--out`).
5. The worker isn't restarted after an `error` reply, only after a kill or a crash.
6. Logging: a RichHandler on the `tapesift` logger at INFO with markup off, added once; worker logs are forwarded over the pipe.
7. A dry run probes and full-hashes (read-only), plans duplicates against earlier pending files, runs resolution and R9's logs, and exits by the same rule (1 if a file fails to probe).
8. A probe-phase crash or error (no ID) writes no marker and repeats on every run, like `ProbeError` (R5).
9. Two registration lines in `cli/__init__.py` (the issue said one): the import, and `app.command()(index)`.
10. The same file under two names is skipped as `same file as <q>`, never DUPLICATE.

## Decision cards
All cards were decided by the owner on 2026-10-20: T3 cards 4-10 after the two-model council and a rebuttal round; T2 cards 1, 2, 3, 11, 12 and 13 directly. Each card ends with its decision, and the rest of this spec follows it.

### Decision needed (T2, process): card 1. Build order, and the dependency on E5's `write_json`
**Context.**
- E7 calls E5's `write_json` (card 3, approved), E3's `transcribe_asset`, E4's `caption_asset`, and E6's `LanceStore` and `OnnxEmbedder`.
- pyright strict fails on an unresolved import, so `pipeline/index.py`, `cli/index.py` and the fixture and models tests can't pass `make check` before those merge.
- `runner/run.py` and `report.py` import only M1 names and `write_json`. Their smoke tests use `quick` (no E3 or E4) and `MemoryStore`.
- Q11 allows up to 6 parallel builders after M1.

**Options.**
- **A. E7 starts after E3, E4, E5 and E6 merge** (not chosen). Pros: one pass, against real glue. Cons: E7 is the critical path to v0.1 (Nov 1), and it starts last.
- **B. Two phases in one draft PR** (assumed above; decided).
  - **Phase 1** starts when M1 and E5 merge: `runner/`, the `__main__.py` guard, `tests/runner_setups.py` without `fake_pipeline`, `test_runner_plan.py` (44), and `test_runner_isolation.py` without its 4 CLI-driven tests (37). That is 81 tests.
  - **Phase 2**, after E3, E4 and E6 merge: `pipeline/`, `cli/` (both files), `fake_pipeline`, the 4 CLI-driven isolation tests (`test_signal_stops_and_resumes` x3, `test_json_stdout_stays_clean`), `test_pipeline_index.py` (16), `test_index_fixtures.py` (15), the models tests (2, `model`), and the spec.md and CHANGELOG lines. That is 35 more, 116 in all.
  - The PR leaves draft only after phase 2.
  - Pros: isolation, resume, #11 and #36 start days earlier. Cons: one rebase; phase 1 can't run the CLI.
- **C. Start now with local stand-ins for missing modules.** Cons: edits outside scope, and throwaway code.

**Hardest to reverse.** None; it's scheduling.
**Recommendation.** B.
**Would change my mind.** E3, E4 and E6 are expected to merge within a day of M1.
**Blocked until answered.** The build start.
**Decided 2026-10-20 (owner):** B. Two phases inside one PR. Phase 1 after M1 and E5 merge (E5 is approved); phase 2 after E3, E4 and E6 merge. E6 card 6 (`StoreError`) must be approved as cited before phase 2.

### Decision needed (T2): card 2. The isolation model: one long-lived spawned worker, killed on a limit
**Context.** One bad file must never fail the batch (AGENTS.md). #36 needs a stuck read to be killable. Models take seconds or more to load. Threads and `signal.alarm` can't interrupt a C call or a stuck syscall.

**Options.**
- **A. One worker process per run** (assumed above). It is started with `spawn`, with SIGINT ignored from exec, stdout sent to stderr, and a parent-death watchdog. It loads models once and handles one request at a time over a `Pipe`. The parent enforces the limits with `poll`, and kills and restarts the worker on a timeout or crash. The parent keeps every side effect: the store, the JSON and the markers. A kill can't leave half-written output, and a segfault or OOM kill fails one file. `spawn`, not `fork`, is the same on macOS and Linux and is safe with threaded native libraries. Pros: a real kill; models loaded once; side effects in one process (spec 733). Cons: pickling across the pipe; a reload after each kill; test `Load`s must be importable by name; `__main__.py` needs a guard.
- **B. One process per file.** Pros: total isolation. Cons: models reload for every file, minutes per file on CPU.
- **C. In-process with a thread or `signal.alarm`.** Pros: simple. Cons: it can't stop a stuck C read (#21 card 3), and a segfault kills the batch.

**Hardest to reverse.** A's `Load` and `Analyze` contract. It's internal until S1 replaces the scheduler.
**Recommendation.** A.
**Would change my mind.** Real runs show model state corrupted after a failure (for example CUDA after an OOM). Then restart the worker after every `error` reply too (a T1 change).
**Blocked until answered.** The build.
**Decided 2026-10-20 (owner):** A.

### Decision needed (T2): card 3. The limits, and how a timeout is recorded (#36)
**Context.** One fixed limit either kills long legitimate files on CPU or waits hours on a dead NAS: a `600 + 10 x duration` limit gives a 3 h file 30 h. Duration is known only after probe. #36 says to record `UNREADABLE` ("timed out after N s"). M1 card 1, approved later the same day, puts every non-`StageError` failure of an identified asset in a failed marker, with the retry cap.

**Options.**
- **A. Deadlines, a ceiling and a no-progress limit** (assumed above).
  - Probe: 120 s, plus `size / 10 MiB/s` when it hashes the whole file.
  - Model load: 3600 s.
  - Index: `min(600 + 5 x duration_s, 12 h)`; 12 h when there is no duration.
  - No progress: 30 min without any worker message. Beats come from every decoded frame and chunk, so a dead NAS is caught in 30 min whatever the length.
  - Constants in `Limits`, not config keys.
  - A probe-phase timeout gives summary code `UNREADABLE`, `timed out after N s` (no ID, like `ProbeError`). An index-phase timeout gives a card 1 marker with `exception: "WorkerTimeout"`, capped at 2 attempts.
  - Pros: bounded on every file; follows both #36 and card 1. Cons: a single backend call over 30 min looks stalled; no knob.
- **B. Deadlines only** (r1). Cons: a dead NAS on a 3 h file waits up to 30 h.
- **C. One fixed limit** (for example 6 h). Cons: kills 3-hour talks on slow CPUs, and is slow on a dead NAS.

**Hardest to reverse.** Promising a config key (none promised here).
**Recommendation.** A.
**Would change my mind.** X1 (#33) measures the cpu profile above 4x realtime, or an ASR call over 15 min on one chunk. Then raise the factor or `stall_s`, by card.
**Blocked until answered.** The Limits rows and the timeout, stall and load tests.
**Decided 2026-10-20 (owner):** A.

### Decision needed (T3, user-facing): card 4. The out-dir layout
**Context.** The issue lists the out-dir layout as T2-or-higher. M1 fixed `store/` (E6) and `failed/<asset_id>.json` (card 1). The ID mode must live somewhere a resume can check (#11). Two runs on one `--out` would race on markers, JSON and LanceDB.

**Options.**
- **A.** (assumed above)
  ```
  out_dir/
    .lock               flock'd for a whole non-dry run; a second run exits 2
    index.json          {"id_mode": "tsid1"} or {"id_mode": "sha256"}
    assets/<id>.json    one schema 1.0 record per asset (E5's write_json); done means present and parseable
    failed/<id>.json    card 1 markers
    store/              LanceDB (E6)
  ```
  The ID is used verbatim in file names, with the `:`. Pros: matches card 1's and the issue's wording; greppable by ID; concurrent runs are refused. Cons: `:` is invalid on NTFS; `flock` may be a no-op on some NFS setups.
- **B.** As A, with `:` replaced by `_` in file names (`asset_file_name`). Cons: names differ from IDs, and card 1's literal path changes.
- **C.** No `index.json`: infer the mode from file names. Cons: an empty index has no mode, and collision-resolved `sha256:` names (card 8) make the inference wrong.

**Hardest to reverse.** Any layout, once users script against it.
**Recommendation.** A.
**Would change my mind.** WSL2 users on `/mnt/c` matter for v0.1. Then B.
**Blocked until answered.** The build.
**Decided 2026-10-20 (owner, after council and rebuttal):** B. This spec follows it throughout:
- file names are `tsid1_<hex>.json` and `sha256_<hex>.json` in `assets/` and `failed/`, with no `:` (`asset_file_name`);
- the canonical ID with `:` lives only inside the JSON, and `scan_assets` trusts it, checking only that it maps to the file name;
- `index.json` is `{"layout": 1, "id_mode": ...}`;
- only `assets/` is documented as public; `.lock`, `index.json` and `failed/` are internal and may change without notice;
- this amends M1 card 1's `failed/<asset_id>.json` literal (scribe).

### Decision needed (T3, output and privacy): card 5. `asset.path` is absolute
**Context.** M1 left it to E7, and `Hit.path` is the same string. The runner compares stored and walked paths to find changed, moved, same and duplicate files. #35 and E5's description flag that paths can reveal user and folder names.

**Options.**
- **A. Absolute, normalized, symlinks not resolved** (`os.path.abspath`) (assumed above). Pros: search results open from any folder; resume doesn't depend on cwd. Cons: home folders and user names appear in JSON. Users strip `asset.path` before sharing; E5 documents it.
- **B. As given on the command line.** Pros: matches spec 269's example (`talks/keynote.mp4`); leaks less. Cons: the same file indexed from two cwds looks like two paths, causing false change or duplicate handling; search output only works from the original cwd.
- **C. Relative to `out_dir`.** Pros: moves with a tree that holds both media and index. Cons: `../../../Volumes/...` paths, and search must re-root them (E6).

**Hardest to reverse.** Any form, once JSON is shared.
**Recommendation.** A. Privacy is handled by documentation now; export with redaction is later work.
**Would change my mind.** The owner wants shareable JSON by default. Then C, with E6 re-rooting.
**Blocked until answered.** The build. The scribe tells E5 to word its description to match.
**Decided 2026-10-20 (owner, after council and rebuttal):** A. Absolute paths. E9's README carries a privacy note, and a future `--redact-paths` export is out of scope here.

### Decision needed (T3, user-facing): card 6. Statuses, the human summary, and the `index --json` shape
**Context.** The issue names the `--json` shape as user-facing. Card 1 says every failure shows in the end-of-run summary (stderr) and in `--json`.

**Options.**
- **A.** (assumed above) Seven statuses: `indexed`, `pending` (dry run), `skipped`, `duplicate`, `failed`, `failed_before`, `deferred`.
  - The JSON is `{"version", "out_dir", "id_mode", "dry_run", "interrupted", "max_media_hours", "total", "counts", "media_hours", "files": [{"path", "status", "asset_id", "code", "stage", "detail"}]}`, with every file in walk order. No timings, so it's deterministic.
  - The human summary goes to stderr, with a retry hint under `failed before`. With `--json`, stdout holds only the JSON.
  - Pros: scriptable; covers every outcome; the top level can grow. Cons: `files` grows with the corpus.
- **B.** As A, but `files` lists only non-indexed files. Cons: scripts can't map paths to IDs.
- **C.** JSON Lines, one object per file as it finishes. Pros: streaming. Cons: no single document; counts are left to the consumer.

**Hardest to reverse.** Any field that ships (spec 212: every `--json` is public).
**Recommendation.** A.
**Would change my mind.** A 100k-file corpus makes the document unwieldy. Then add C later as `--jsonl` (additive).
**Blocked until answered.** The build.
**Decided 2026-10-20 (owner, after council and rebuttal):** A, plus a top-level `"version"` key (here `1`, the document's format version) and no `last-run.json`.

### Decision needed (T3, CLI flag): card 7. Ship `--full-hash` in v0.1
**Context.** ADR 0012 decided a full-hash mode exists "on request", and #11 names `--full-hash`. Q10 B listed only `--max-hours` and `--dry-run`. `probe(full_hash=True)` exists (E1). Without a flag, v0.1 can't create a `sha256` index, so #11's "resume with the other mode exits 2" can be tested only by hand-writing `index.json`.

**Options.**
- **A. Ship `--full-hash`** (assumed above). It passes `full_hash` to probe and records `sha256` in `index.json`. Pros: delivers ADR 0012's option; #11 is tested end to end; small. Cons: a public flag can't be removed later.
- **B. No flag.** `index.json` still records `tsid1`, and the guard is tested with a planted file. Pros: no new surface. Cons: ADR 0012's promise slips, and the guard is dead code in v0.1.
- **C. A config key `full_hash`.** Cons: config.py is M1's; it's an interface change.

**Hardest to reverse.** A.
**Recommendation.** A.
**Would change my mind.** The owner wants v0.1's flag set to be exactly Q10's.
**Blocked until answered.** The option, `test_full_hash_mode`, `test_id_mode_mismatch_exits_2` and line 217.
**Decided 2026-10-20 (owner, after council and rebuttal):** A. `--full-hash` ships.

### Decision needed (T3, asset IDs): card 8. A tsid1 collision indexes the later file under its `sha256:` ID
**Context.** #11 says that when tsid1 IDs match but full hashes differ, both files are indexed and the collision is logged. Both can't be `assets/<tsid1>.json`. ADR 0012 says indexes never mix modes.

**Options.**
- **A. The later file (walk order) gets its full `sha256:` ID** (assumed above).
  - `index.json` stays `tsid1`; "never mix modes" is read as "never resume across modes".
  - Reruns are deterministic: the file's stored `sha256:` ID is re-checked first, even if the original is deleted.
  - A byte copy of the later file is a DUPLICATE of it, not an overwrite.
  - Pros: real, verifiable IDs; no new scheme. Cons: a tsid1 index can hold a few `sha256:` IDs, and which file gets which depends on walk order.
- **B. A derived tsid1, for example `tsid1:sha256(tsid1 || full)`.** Cons: an ID that matches no documented scheme, against ADR 0012's versioning.
- **C. Index the first file only, and fail the second with the reason.** Cons: violates #11.

**Hardest to reverse.** B (an undocumented ID form in user data).
**Recommendation.** A. The scribe adds one line to ADR 0012's Consequences after the decision: "a tsid1 collision is resolved by indexing the later file under its sha256: ID".
**Would change my mind.** The owner reads "never mix" as per-asset. Then C, with #11 amended.
**Blocked until answered.** The three collision tests.
**Decided 2026-10-20 (owner, after council and rebuttal):** A. The scribe amends ADR 0012: a tsid1 collision gives the later file its `sha256:` ID; resuming an index across ID modes is refused.

### Decision needed (T3, flag semantics): card 9. What the media-hours budget flag means
**Context.** Q10 B ships the flag without defining it. The dry run reports media hours.

**Options.**
- **A. A media-hours budget per run** (assumed above).
  - Before each probe, stop starting new files once the media hours indexed in this run (planned, in a dry run) reach H.
  - The rest are `deferred`, unprobed, and don't affect the exit code.
  - The crossing file finishes, so a file longer than H still indexes and every run makes progress.
  - Skipped, duplicate, failed and failed_before files don't count; a missing duration counts 0.
  - Pros: deterministic and testable; matches the dry run's hours. Cons: not a wall-clock bound.
- **B. A wall-clock budget.** Pros: "run overnight for 8 hours". Cons: nondeterministic; needs a kill or a wait.
- **C. Refuse to start when the planned hours exceed H.** Cons: nothing gets indexed.

**Hardest to reverse.** Any meaning, once shipped.
**Recommendation.** A.
**Would change my mind.** The owner meant time-based cost control (B). Then a separate `--max-wall-hours` later.
**Blocked until answered.** `test_max_media_hours_defers_rest` and line 217.
**Decided 2026-10-20 (owner, after council and rebuttal):** A, with the flag named `--max-media-hours` (help: "Stop starting new files after H hours of media."). Spec line 217 uses that name. The S1 rule (in-flight files count toward the budget) is in Risks.

### Decision needed (T3, CLI behaviour): card 10. Ctrl-C
**Context.** Spec 38 says a kill loses at most the in-flight file. Spec 212's codes 0-3 describe finished runs.

**Options.**
- **A.** (assumed above) The first Ctrl-C:
  - kills the worker at once (it has ignored SIGINT since exec);
  - drops the in-flight file with no marker, since it's not the file's fault;
  - prints the partial summary (or JSON with `interrupted: true`);
  - exits 130 (128 + SIGINT, the POSIX convention).

  A JSON is never partial: E5 writes it atomically and last, and store rows without a JSON are redone on resume. Spec 212 gets the 130 sentence (in scope). Pros: immediate; safe; scripts can tell it apart from code 1. Cons: a fifth exit code.
- **B. Finish the in-flight file, then stop; a second Ctrl-C aborts.** Pros: no wasted work. Cons: on an hour-long file, Ctrl-C looks broken.
- **C. Exit 1 (Click's "Aborted!").** Cons: same as "some files failed".

**Hardest to reverse.** The exit code, once scripts rely on it.
**Recommendation.** A.
**Would change my mind.** Users want graceful finish (B) as the default.
**Blocked until answered.** The interrupt tests and the line 212 edit.
**Decided 2026-10-20 (owner, after council and rebuttal):** A, extended:
- SIGTERM and SIGHUP are handled like SIGINT, and exit 143 and 129;
- the three signals are blocked during the parent's store writes, `write_json` and marker writes, and land right after;
- a second signal while the summary prints exits at once (`exit_on_next_signal`).

### Decision needed (T2): card 11. What the walk includes
**Context.**
- spec.md 299 names `.DS_Store` in a folder as a stray file to "skip with the exact reason" (UNREADABLE). M1 left open whether that alone makes the exit code 1.
- Symlinked folders can loop.
- Linux names with invalid UTF-8 can't be stored faithfully: E5 writes them with `?`, so the path wouldn't reopen.
- `os.walk` skips an unreadable subfolder silently.

**Options.**
- **A.** (assumed above)
  - Inside folders, skip names starting with `.` (`.DS_Store`, `._*`, `.git`), with one INFO line per skipped entry.
  - Probe everything else, so `notes.txt` is UNREADABLE and exits 1. Named PATHs are always probed.
  - Follow symlinked files; don't enter symlinked folders.
  - Undecodable names and unlistable folders become failed `UNREADABLE` entries with exact reasons.
  - spec.md 299's example changes to `notes.txt` and states the hidden-entry rule (in scope).
  - Pros: Mac folders don't exit 1; no loops; nothing is skipped silently. Cons: a real hidden media file is skipped unless named.
- **B. Probe everything, dotfiles included.** Cons: every Mac folder exits 1 because of `.DS_Store`.
- **C. An extension allow-list.** Cons: extension-based, which #21 removed on purpose; misnamed media are skipped.

**Hardest to reverse.** C.
**Recommendation.** A.
**Would change my mind.** Users keep media in dot-folders.
**Blocked until answered.** The walk tests and the line 299 edit.
**Decided 2026-10-20 (owner):** A.

### Decision needed (T2): card 12. A file whose ID was indexed at a path that no longer exists (moved)
**Context.** Resume is by content hash (spec 38), so a moved file shouldn't be reprocessed. Its JSON and store rows still name the old path. M1 has no way to rebuild an `AssetRecord` from JSON to re-upsert it.

**Options.**
- **A. Skip it, with detail `already indexed as <old>`** (assumed above). The old path stays in the JSON and the store until S2. Pros: no rework; visible in `--json`. Cons: search shows the old path.
- **B. Re-index it at the new path** (delete the old record first). Pros: correct paths. Cons: reprocesses moved libraries in full, against spec 38.
- **C. Rewrite only the JSON's `asset.path`.** Cons: the store still shows the old path, so the two disagree.

**Hardest to reverse.** None; S2 can migrate.
**Recommendation.** A.
**Would change my mind.** E9 or X1 users routinely reorganize folders between runs. Then B.
**Blocked until answered.** `test_moved_file_is_skipped`.
**Decided 2026-10-20 (owner):** A.

### Decision needed (T2, dependency): card 13. Use rich directly for the progress bar and log handler
**Context.** The issue says "rich comes in through typer, and tqdm through faster-whisper. Use what is installed, and raise a card if anything new is needed". `rich` 15.0.0 is installed because typer 0.27.3 requires it unconditionally. typer re-exports no progress or logging API; `typer.rich_utils` is private help formatting, so importing rich directly makes it an undeclared direct dependency. Only M1 edits `pyproject.toml` in v0.1 (Q2).

**Options.**
- **A. Import rich directly, undeclared,** with a `ponytail:` comment. It is declared by the next spec that edits `pyproject.toml` (E8 at the latest). The import tests fail loudly if it disappears. Pros: no `pyproject.toml` edit now; the issue's intent. Cons: a transitive pin decides rich's version until then.
- **B. Declare `rich>=15.0.0` now,** in this PR. Pros: honest metadata. Cons: edits `pyproject.toml` and `uv.lock` outside M1, against Q2's rule; a conflict with any parallel lock change.
- **C. No rich:** one INFO log line per file instead of a bar. Pros: no dependency question. Cons: the issue asks for a progress bar.

**Hardest to reverse.** B (a declared dependency).
**Recommendation.** A.
**Would change my mind.** The owner prefers honest metadata now. Then B, in M1.
**Blocked until answered.** `cli/index.py`'s progress and logging.
**Decided 2026-10-20 (owner):** rich is declared as a direct dependency in M1 (in effect B, done in M1, not here). E7 imports it as a declared dependency. Nothing here edits `pyproject.toml`.
