"""E7 runner v0 (spec 37-38, M1 R5 and card 1, #11, #36): walk the inputs, run each file in one
killable worker process, resume by asset ID, write out_dir, and return the Summary. The only
module with side effects on out_dir. Imports no backend: models load in the worker via `load`."""

from __future__ import annotations

import dataclasses
import fcntl
import json
import logging
import multiprocessing
import os
import re
import signal
import sys
import threading
import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Final, Literal, NoReturn, TypedDict, cast

from tapesift import __version__
from tapesift.config import Config, ModelLoadError
from tapesift.media.types import AssetInfo
from tapesift.runner.report import FileResult, Summary
from tapesift.schema.records import AssetRecord
from tapesift.store.types import Store
from tapesift.warning_codes import WarningCode

log = logging.getLogger(__name__)

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
INTERRUPT_SIGNALS: Final = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)  # card 10


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


def install_interrupt_handlers() -> Callable[[], None]:
    """Each of INTERRUPT_SIGNALS raises Interrupted(signum). Returns a function that restores the
    previous handlers. Called by the CLI, not by run_index."""

    def handler(signum: int, frame: object) -> None:
        raise Interrupted(signum)

    old = {s: signal.signal(s, handler) for s in INTERRUPT_SIGNALS}

    def restore() -> None:
        for s, h in old.items():
            signal.signal(s, h)

    return restore


def exit_on_next_signal(signum: int) -> None:
    """After the first interruption: any further INTERRUPT_SIGNALS calls os._exit(128 + signum)
    at once (card 10: a second signal while the summary prints exits immediately)."""

    def handler(_signum: int, _frame: object) -> None:
        os._exit(128 + signum)

    for s in INTERRUPT_SIGNALS:
        signal.signal(s, handler)


class OutDirError(Exception):
    """out_dir can't be used: the other ID mode (#11), an index file this version can't read,
    or another run holds the lock. The CLI exits 2."""


def display(p: str | os.PathLike[str]) -> str:
    return os.fsencode(p).decode("utf-8", "backslashreplace")


def walk(paths: Sequence[Path]) -> list[Path | FileResult]:
    out: list[Path | FileResult] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        if p in seen:
            return
        seen.add(p)
        try:
            p.encode("utf-8")
        except UnicodeEncodeError:
            out.append(
                FileResult(
                    display(p),
                    "failed",
                    None,
                    None,
                    WarningCode.UNREADABLE,
                    None,
                    "file name is not valid UTF-8",
                )
            )
        else:
            out.append(Path(p))

    def onerror(e: OSError) -> None:
        out.append(
            FileResult(
                display(e.filename or ""),
                "failed",
                None,
                None,
                WarningCode.UNREADABLE,
                None,
                f"cannot list folder: {e.strerror}",
            )
        )

    for raw in paths:
        a = os.path.abspath(raw)  # noqa: PTH100  absolute, normalized, symlinks kept (card 5)
        if not Path(a).is_dir():
            add(a)
            continue
        for root, dirnames, filenames in os.walk(a, onerror=onerror, followlinks=False):
            for n in [n for n in (*dirnames, *filenames) if n.startswith(".")]:
                log.info(f"skipping hidden {display(str(Path(root) / n))}")
            dirnames[:] = sorted(n for n in dirnames if not n.startswith("."))
            for n in sorted(n for n in filenames if not n.startswith(".")):
                add(str(Path(root) / n))
    return out


def _write_small_json(path: Path, obj: object) -> None:
    """Markers and index.json (and, until E5 merges, asset JSON): temp file, fsync, rename,
    fsync of the folder."""
    tmp = path.with_name(f".tapesift-{os.getpid()}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(
                (json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")
            )
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        log.warning(f"cannot sync folder {path.parent}: {e}")


def write_json(record: AssetRecord, path: Path) -> None:
    """The single touchpoint with E5 (#28). ponytail: stand-in, not schema 1.0. When E5 merges,
    delete this function and add `from tapesift.schema.output import write_json` above."""
    _write_small_json(path, dataclasses.asdict(record))


@contextmanager
def open_out_dir(out_dir: Path, mode: IdMode, *, create: bool) -> Generator[None]:
    fd: int | None = None
    try:
        if create:
            out_dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(out_dir / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OutDirError(f"{out_dir} is in use by another tapesift index run") from None
        fresh = _check_mode(out_dir, mode)
        if create:
            (out_dir / ASSETS_DIR).mkdir(exist_ok=True)
            (out_dir / FAILED_DIR).mkdir(exist_ok=True)
            if fresh:
                _write_small_json(out_dir / INDEX_FILE, {"layout": LAYOUT, "id_mode": mode})
            for d in (out_dir, out_dir / ASSETS_DIR, out_dir / FAILED_DIR):
                for tmp in d.glob(TEMP_GLOB):  # left by a hard kill
                    tmp.unlink(missing_ok=True)
        yield
    finally:
        if fd is not None:
            os.close(fd)


def _check_mode(out_dir: Path, mode: IdMode) -> bool:
    """True when index.json says nothing usable and the folder holds no asset or marker file."""
    try:
        doc: object = json.loads((out_dir / INDEX_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        doc = None
    if isinstance(doc, dict):
        d = cast("dict[str, object]", doc)
        existing = d.get("id_mode")
        if d.get("layout") == LAYOUT and existing in ("tsid1", "sha256"):
            if existing == mode:
                return False
            raise OutDirError(
                f"{out_dir} is a {existing} index; this run uses {mode} IDs. "
                f"Rerun {'with' if existing == 'sha256' else 'without'} --full-hash, "
                "or use another --out."
            )
    for sub in (ASSETS_DIR, FAILED_DIR):
        if any(ASSET_FILE_RE.fullmatch(f.name) for f in (out_dir / sub).glob("*.json")):
            raise OutDirError(
                f"{out_dir / INDEX_FILE}: not an index this version of tapesift can resume; "
                "use another --out."
            )
    return True


def scan_assets(assets_dir: Path) -> dict[str, str]:
    """Asset id -> recorded asset.path, for every parseable asset file."""
    found: dict[str, str] = {}
    for f in sorted(assets_dir.glob("*.json")):
        if not ASSET_FILE_RE.fullmatch(f.name):
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            aid, p = doc["asset"]["id"], doc["asset"]["path"]
            if not (isinstance(aid, str) and isinstance(p, str)):
                raise TypeError("asset id and path must be strings")
            if asset_file_name(aid) != f.name:
                raise ValueError("file name does not match asset id")
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning(f"ignoring unreadable {f.name}: {type(e).__name__}")
            continue
        found[aid] = p
    return found


def read_marker(path: Path) -> Marker | None:
    try:
        doc: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        doc = None
    if isinstance(doc, dict):
        d = cast("dict[str, object]", doc)
        n = d.get("attempts")
        if (
            set(d) == set(Marker.__annotations__)
            and isinstance(n, int)
            and not isinstance(n, bool)
            and n >= 1
            and all(isinstance(v, str) for k, v in d.items() if k != "attempts")
        ):
            return cast("Marker", d)
    log.warning(f"ignoring malformed marker {path.name}")
    return None


def retry_allowed(marker: Marker | None, version: str) -> bool:
    return marker is None or marker["tapesift"] != version or marker["attempts"] < MAX_ATTEMPTS


def next_attempts(marker: Marker | None, version: str) -> int:
    return 1 if marker is None or marker["tapesift"] != version else marker["attempts"] + 1


@contextmanager
def _signals_deferred() -> Generator[None]:
    """Card 10: a signal that arrives meanwhile is recorded and raised right after. T1: swaps the
    Python handlers instead of pthread_sigmask, which misses a signal the OS hands to another
    thread. Main thread only."""
    hit: list[int] = []

    def record(signum: int, frame: object) -> None:
        hit.append(signum)

    old = {s: signal.signal(s, record) for s in INTERRUPT_SIGNALS}
    try:
        yield
    finally:
        for s, h in old.items():
            signal.signal(s, h)
        if hit:
            signal.raise_signal(hit[0])


# ---- the worker (cards 2 and 3) ------------------------------------------------------------


def _worker_main(conn: Connection[Any, Any], cfg: Config, load: Load | None) -> None:
    os.dup2(2, 1)  # anything a library prints goes to stderr; --json stdout stays clean
    sys.stdout = sys.stderr
    ppid = os.getppid()

    def watchdog() -> None:  # a worker never outlives a killed parent
        while True:
            time.sleep(1.0)
            if os.getppid() != ppid:
                os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    lock = threading.Lock()

    def send(msg: tuple[Any, ...]) -> None:
        with lock:
            conn.send(msg)

    class Forward(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                send(
                    (
                        "log",
                        record.name,
                        record.levelno,
                        record.getMessage(),
                        getattr(record, "asset_id", None),
                        getattr(record, "stage", None),
                    )
                )
            except Exception:
                self.handleError(record)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(Forward())

    from tapesift.media.asset_id import asset_id
    from tapesift.media.probe import probe
    from tapesift.media.types import ProbeError

    analyze: Analyze | None = None
    if load is not None:
        try:
            analyze = load(cfg)
        except ModelLoadError as e:
            send(("load_error", str(e)))
            return
    send(("ready",))

    stage = "worker"
    last_beat = 0.0

    def on_stage(name: StageName) -> None:
        nonlocal stage
        stage = name
        send(("stage", name))

    def beat() -> None:
        nonlocal last_beat
        now = time.monotonic()
        if now - last_beat >= BEAT_EVERY_S:
            last_beat = now
            send(("beat",))

    while True:
        try:
            req = conn.recv()
        except (EOFError, OSError):
            return
        kind = req[0]
        stage = {"probe": "probe", "hash": "hash"}.get(kind, "worker")
        try:
            if kind == "probe":
                send(("asset", probe(req[1], full_hash=req[2])))
            elif kind == "hash":
                send(("full_id", asset_id(req[1], full=True)))
            elif analyze is not None:
                send(("record", analyze(req[1], on_stage, beat)))
        except ProbeError as e:
            send(("probe_error", e.warning.detail))
        except Exception as e:
            send(("error", stage, type(e).__name__, f"{type(e).__name__}: {e}"))


class _Timeout(Exception):
    pass


class _Collision(Exception):
    pass


class _Crashed(Exception):
    def __init__(self, exitcode: int | None) -> None:
        super().__init__(exitcode)
        self.exitcode = exitcode


def _reemit(msg: tuple[Any, ...]) -> None:
    _, name, levelno, message, aid, stage = msg
    logging.getLogger(name).log(levelno, message, extra={"asset_id": aid, "stage": stage})


class _Worker:
    """One spawned process at a time; started lazily, restarted after a kill or a crash."""

    def __init__(self, cfg: Config, load: Load | None, limits: Limits) -> None:
        self.cfg, self.load, self.limits = cfg, load, limits
        self.proc: BaseProcess | None = None
        self.conn: Connection[Any, Any] | None = None
        self.stage = "worker"

    def start(self) -> None:
        if self.proc is not None:
            return
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        proc = ctx.Process(target=_worker_main, args=(child, self.cfg, self.load), daemon=True)
        # The child must start with these ignored (they survive exec): a Ctrl-C or hangup
        # reaches the parent alone, and the parent kills the worker (card 10).
        saved = [(s, signal.signal(s, signal.SIG_IGN)) for s in INTERRUPT_SIGNALS]
        try:
            proc.start()
        finally:
            for s, h in saved:
                signal.signal(s, h)
        child.close()
        self.proc, self.conn = proc, parent
        deadline = time.monotonic() + self.limits.load_s
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not parent.poll(left):
                self.kill()
                raise ModelLoadError(f"models did not load within {self.limits.load_s:g} s")
            try:
                msg = parent.recv()
            except (EOFError, OSError):
                proc.join(KILL_JOIN_S)
                code = proc.exitcode
                self.kill()
                raise ModelLoadError(
                    f"worker exited with code {code} while loading models"
                ) from None
            if msg[0] == "log":
                _reemit(msg)
            elif msg[0] == "ready":
                return
            elif msg[0] == "load_error":
                self.kill()
                raise ModelLoadError(msg[1])

    def ask(
        self, req: tuple[Any, ...], limit_s: float, stall_s: float | None = None
    ) -> tuple[Any, ...]:
        self.start()
        conn, proc = self.conn, self.proc
        if conn is None or proc is None:
            raise RuntimeError("worker not started")
        self.stage = {"probe": "probe", "hash": "hash"}.get(req[0], "worker")
        begin = last = time.monotonic()
        try:
            conn.send(req)
        except OSError:
            self._crash(proc)
        while True:
            now = time.monotonic()
            if now >= begin + limit_s:
                self.kill()
                raise _Timeout(f"timed out after {limit_s:g} s")
            if stall_s is not None and now >= last + stall_s:
                self.kill()
                raise _Timeout(f"no progress for {stall_s:g} s")
            until = begin + limit_s if stall_s is None else min(begin + limit_s, last + stall_s)
            if not conn.poll(until - now):
                continue
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                self._crash(proc)
            last = time.monotonic()
            if msg[0] == "log":
                _reemit(msg)
            elif msg[0] == "stage":
                self.stage = msg[1]
            elif msg[0] != "beat":
                return cast("tuple[Any, ...]", msg)

    def _crash(self, proc: BaseProcess) -> NoReturn:
        proc.join(KILL_JOIN_S)
        code = proc.exitcode
        self.kill()
        raise _Crashed(code)

    def kill(self) -> None:
        proc, conn = self.proc, self.conn
        self.proc = self.conn = None
        if proc is None or conn is None:
            return
        proc.kill()
        proc.join(KILL_JOIN_S)
        if proc.is_alive():
            # ponytail: one abandoned worker per stuck file; abort the run after 3 by card.
            log.warning(f"worker {proc.pid} did not exit after SIGKILL; abandoning it")
        else:
            proc.close()
        conn.close()

    def close(self) -> None:
        proc, conn = self.proc, self.conn
        self.proc = self.conn = None
        if proc is None or conn is None:
            return
        conn.close()  # the worker sees EOF and returns
        proc.join(KILL_JOIN_S)
        if proc.is_alive():
            proc.kill()
            proc.join(KILL_JOIN_S)
        if not proc.is_alive():
            proc.close()


class _Fail(Exception):
    """A per-file failure. `exception` set: also write a card 1 marker for the file's ID."""

    def __init__(
        self,
        stage: str,
        detail: str,
        code: WarningCode | None = None,
        exception: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.stage, self.detail, self.code, self.exception = stage, detail, code, exception


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
    mode: IdMode = "sha256" if full_hash else "tsid1"
    out = cfg.out_dir
    dry = open_store is None
    lim = limits or Limits()
    results: list[FileResult] = []
    entries: list[Path | FileResult] = []
    interrupted_by: int | None = None
    hours = 0.0
    full: dict[str, str] = {}  # full IDs by path

    with open_out_dir(out, mode, create=not dry):
        indexed = scan_assets(out / ASSETS_DIR)  # asset id -> path
        by_path = {p: i for i, p in indexed.items()}
        store = open_store(cfg) if open_store is not None else None
        worker = _Worker(cfg, None if dry else load, lim)

        def write_marker(p: Path, aid: str, f: _Fail) -> None:
            mpath = out / FAILED_DIR / asset_file_name(aid)
            with _signals_deferred():
                try:
                    marker: Marker = {
                        "path": str(p),
                        "stage": f.stage,
                        "exception": f.exception or "",
                        "error": f.detail,
                        "attempts": next_attempts(read_marker(mpath), __version__),
                        "tapesift": __version__,
                    }
                    _write_small_json(mpath, marker)
                except OSError as e:
                    log.error(f"cannot write failed marker for {p}: {e}")

        def call(req: tuple[Any, ...], stage: str, size: int, full_read: bool) -> tuple[Any, ...]:
            try:
                r = worker.ask(req, lim.probe_deadline(size, full=full_read))
            except _Timeout as e:
                raise _Fail(stage, str(e), WarningCode.UNREADABLE) from None
            except _Crashed as e:
                raise _Fail(stage, f"WorkerCrashed: worker exited with code {e.exitcode}") from None
            if r[0] == "probe_error":
                raise _Fail(stage, r[1], WarningCode.UNREADABLE)
            if r[0] == "error":
                raise _Fail(stage, r[3])
            return r

        def fid(p: Path) -> str:
            if str(p) not in full:
                try:
                    size = p.stat().st_size
                except OSError as e:
                    raise _Fail("hash", str(e.strerror), WarningCode.UNREADABLE) from None
                full[str(p)] = call(("hash", p), "hash", size, True)[1]
            return full[str(p)]

        def process(p: Path) -> FileResult:
            nonlocal hours
            d, sp = display(p), str(p)
            final: str | None = None
            dur: float | None = None
            stage = "probe"
            try:
                try:
                    size = p.stat().st_size if full_hash else 0
                except OSError as e:
                    raise _Fail("probe", str(e.strerror), WarningCode.UNREADABLE) from None
                asset: AssetInfo = call(("probe", p, full_hash), "probe", size, full_hash)[1]
                dur = asset.duration_s
                stage = "hash"  # a failure before the worker runs: ID resolution

                def done(
                    status: Literal["skipped", "duplicate"], aid: str, detail: str | None
                ) -> FileResult:
                    code = WarningCode.DUPLICATE if status == "duplicate" else None
                    return FileResult(d, status, aid, dur, code, None, detail)

                def match(i: str) -> FileResult | None:
                    q = indexed.get(i)
                    if q is None:
                        return None
                    if q == sp:
                        return done("skipped", i, None)
                    if not Path(q).exists():
                        return done("skipped", i, f"already indexed as {q}")
                    if p.samefile(q):
                        return done("skipped", i, f"same file as {q}")
                    if i.startswith("sha256:") or fid(p) == fid(Path(q)):
                        return done("duplicate", i, f"same content as {q}")
                    raise _Collision

                old = by_path.get(sp)
                outcome: FileResult | None
                if (
                    mode == "tsid1"
                    and old is not None
                    and old.startswith("sha256:")
                    and (fid(p) == old)
                ):
                    outcome = done("skipped", old, None)  # a collision-resolved file, unchanged
                else:
                    try:
                        outcome = match(asset.id)
                    except _Collision:
                        q = indexed[asset.id]
                        log.warning(
                            f"tsid1 collision: {p} and {q} share {asset.id} but their sha256 "
                            f"differ; indexing {p} as {fid(p)}"
                        )
                        asset = dataclasses.replace(asset, id=fid(p))
                        outcome = match(asset.id)
                final = (outcome.asset_id if outcome else None) or asset.id
                if not dry and store is not None and old is not None and old != final:
                    stage = "store"  # the file changed: drop its old record before indexing
                    with _signals_deferred():
                        store.delete(old)
                        (out / ASSETS_DIR / asset_file_name(old)).unlink(missing_ok=True)
                        indexed.pop(old, None)
                        by_path.pop(sp, None)
                if outcome is not None:
                    return outcome
                m = read_marker(out / FAILED_DIR / asset_file_name(final))
                if not retry_allowed(m, __version__) and m is not None:
                    return FileResult(
                        d,
                        "failed_before",
                        final,
                        dur,
                        None,
                        None,
                        f"failed before ({m['attempts']} attempts on {__version__}); not retried",
                    )
                if store is None:
                    indexed[final], by_path[sp] = sp, final  # planned: later copies are duplicates
                    hours += dur or 0.0
                    return FileResult(d, "pending", final, dur)
                stage = "worker"
                try:
                    r = worker.ask(("index", asset), lim.index_deadline(dur), stall_s=lim.stall_s)
                except _Timeout as e:
                    raise _Fail(
                        worker.stage, f"WorkerTimeout: {e}", None, "WorkerTimeout"
                    ) from None
                except _Crashed as e:
                    raise _Fail(
                        worker.stage,
                        f"WorkerCrashed: worker exited with code {e.exitcode}",
                        None,
                        "WorkerCrashed",
                    ) from None
                if r[0] == "error":
                    raise _Fail(r[1], r[3], None, r[2])
                record: AssetRecord = r[1]
                with _signals_deferred():
                    stage = "store"
                    store.upsert(record)
                    stage = "write"
                    write_json(record, out / ASSETS_DIR / asset_file_name(record.asset.id))
                    (out / FAILED_DIR / asset_file_name(final)).unlink(missing_ok=True)
                    indexed[final], by_path[sp] = sp, final
                    hours += dur or 0.0
                    log.info(f"indexed {p}", extra={"asset_id": final, "stage": "write"})
                    res = FileResult(d, "indexed", final, dur)
                    results.append(res)
                return res
            except ModelLoadError:
                raise  # a restarted worker could not load: the run stops (exit 3)
            except _Fail as f:
                if f.exception is not None and final is not None and not dry:
                    write_marker(p, final, f)
                return FileResult(
                    d, "failed", final if f.exception else None, dur, f.code, f.stage, f.detail
                )
            except Exception as e:
                f = _Fail(stage, f"{type(e).__name__}: {e}", None, type(e).__name__)
                if final is not None and not dry:
                    write_marker(p, final, f)
                return FileResult(d, "failed", final, dur, None, stage, f.detail)

        try:
            worker.start()
            entries = walk(paths)
            total = len(entries)
            for i, entry in enumerate(entries):
                if progress:
                    name = Path(entry.path).name if isinstance(entry, FileResult) else entry.name
                    progress(i, total, display(name))
                if isinstance(entry, FileResult):
                    results.append(entry)
                    continue
                if max_media_hours is not None and hours >= max_media_hours * 3600:
                    results += [
                        FileResult(
                            e.path if isinstance(e, FileResult) else display(e),
                            "deferred",
                            None,
                            None,
                        )
                        for e in entries[i:]
                    ]
                    break
                res = process(entry)
                if res.status != "indexed":  # indexed results are appended inside the write block
                    results.append(res)
            if progress:
                progress(total, total, "")
        except KeyboardInterrupt as e:
            worker.kill()
            interrupted_by = e.signum if isinstance(e, Interrupted) else int(signal.SIGINT)
        finally:
            worker.close()
    out_abs = os.path.abspath(out)  # noqa: PTH100
    return Summary(
        out_abs, mode, dry, interrupted_by, max_media_hours, len(entries), tuple(results)
    )
