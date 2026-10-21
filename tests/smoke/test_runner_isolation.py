"""E7 runner v0 with real worker processes and the real probe (docs/specs/30-runner.md,
test_runner_isolation.py, phase 1: no CLI). Models are fakes (ADR 0008): `quick` does no decoding.
asset.path and asset.id are the only fields asserted in asset JSONs (E5's writer is not merged)."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from tests.runner_setups import FAULTS_ENV, SIX, SPY_ENV, SpyStore, broken, dies, quick, slowload
from tests.smoke.conftest import FIXTURES

from tapesift import __version__
from tapesift.config import Config, ModelLoadError
from tapesift.media.asset_id import asset_id
from tapesift.runner.report import FileResult, Summary
from tapesift.runner.run import (
    Limits,
    Load,
    OutDirError,
    asset_file_name,
    install_interrupt_handlers,
    run_index,
)
from tapesift.warning_codes import WarningCode

REPO_ROOT = Path(__file__).parents[2]
NAMES = ("a.mp4", "b.mp4", "c.mp4", "d.mp4", "e.mp4", "f.mp4")
MiB = 2**20


class Env:
    """One tmp_path: inputs, an out dir, a spy file, a SpyStore, and a run() helper."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = tmp_path
        self.inp = tmp_path / "in"
        self.inp.mkdir()
        self.out = tmp_path / "out"
        self.spy_file = tmp_path / "spy.txt"
        self.spy = SpyStore()
        self.cfg = Config(out_dir=self.out)
        self.progress: list[tuple[int, int, str]] = []
        self._seen = 0
        self.mp = monkeypatch
        monkeypatch.setenv(SPY_ENV, str(self.spy_file))
        monkeypatch.delenv(FAULTS_ENV, raising=False)

    def put(self, dest: str, src: str = "clean.mp4") -> Path:
        p = self.inp / dest
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURES / src, p)
        return p

    def six(self) -> list[Path]:
        return [self.put(n, s) for n, s in zip(NAMES, SIX, strict=True)]

    def faults(self, spec: str | None) -> None:
        if spec is None:
            self.mp.delenv(FAULTS_ENV, raising=False)
        else:
            self.mp.setenv(FAULTS_ENV, spec)

    def run(
        self,
        paths: list[Path] | None = None,
        *,
        load: Load = quick,
        dry: bool = False,
        **kw: Any,
    ) -> Summary:
        self.progress = []
        return run_index(
            paths or [self.inp],
            self.cfg,
            load=load,
            open_store=None if dry else (lambda _c: self.spy),
            progress=lambda d, t, n: self.progress.append((d, t, n)),
            **kw,
        )

    def lines(self) -> list[str]:
        if not self.spy_file.exists():
            return []
        return self.spy_file.read_text(encoding="utf-8").splitlines()

    def new_analyses(self) -> list[str]:
        """File-name lines the workers appended since the last call (pid lines dropped)."""
        lines = self.lines()
        new, self._seen = lines[self._seen :], len(lines)
        return [ln for ln in new if not ln.startswith("pid:")]

    def mark_seen(self) -> None:
        self._seen = len(self.lines())

    @property
    def assets(self) -> list[Path]:
        return sorted((self.out / "assets").glob("*.json"))

    def marker(self, p: Path) -> Path:
        return self.out / "failed" / asset_file_name(asset_id(p))

    def markers(self) -> list[Path]:
        return sorted((self.out / "failed").glob("*.json"))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


def by_name(s: Summary) -> dict[str, FileResult]:
    return {Path(r.path).name: r for r in s.files}


def statuses(s: Summary) -> dict[str, str]:
    return {n: r.status for n, r in by_name(s).items()}


def read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def snapshot(root: Path) -> dict[str, tuple[int, int] | None]:
    return {
        str(p.relative_to(root)): ((st := p.stat()).st_mtime_ns, st.st_size)
        if p.is_file()
        else None
        for p in sorted(root.rglob("*"))
    }


def test_indexes_each_file_once(env: Env) -> None:
    env.six()
    s = env.run()
    assert [(r.status, Path(r.path).name) for r in s.files] == [("indexed", n) for n in NAMES]
    ids = [r.asset_id for r in s.files]
    assert len(set(ids)) == 6
    names = {asset_file_name(str(i)) for i in ids}
    assert {p.name for p in env.assets} == names
    assert not any(":" in n for n in names)
    for r in s.files:
        doc = read_json(env.out / "assets" / asset_file_name(str(r.asset_id)))
        assert doc["asset"]["id"] == r.asset_id
        assert doc["asset"]["path"] == str(env.inp / Path(r.path).name)
        assert Path(doc["asset"]["path"]).is_absolute()
    assert read_json(env.out / "index.json") == {"layout": 1, "id_mode": "tsid1"}
    assert env.spy.upserts == ids
    assert env.progress == [(i, 6, n) for i, n in enumerate(NAMES)] + [(6, 6, "")]
    assert list(env.out.rglob(".tapesift-*.tmp")) == []
    assert s.exit_code == 0


def test_rerun_processes_nothing(env: Env) -> None:
    env.six()
    env.run()
    env.new_analyses()
    s = env.run()
    assert s.counts()["skipped"] == 6
    assert env.new_analyses() == []
    assert len(env.spy.upserts) == 6


def test_bad_file_fails_alone(env: Env) -> None:
    env.six()
    shutil.copyfile(FIXTURES / "not_media.txt", env.inp / "c0.txt")
    s = env.run()
    bad = by_name(s)["c0.txt"]
    assert bad.status == "failed"
    assert bad.code == WarningCode.UNREADABLE
    assert bad.detail == "InvalidDataError: Invalid data found when processing input"
    assert bad.asset_id is None
    assert [n for n, st in statuses(s).items() if st != "indexed"] == ["c0.txt"]
    assert env.markers() == []
    assert s.exit_code == 1


def test_boom_marker_retry_cap_then_success(env: Env) -> None:
    paths = env.six()
    b = paths[1]
    env.faults("b.mp4:boom")
    s = env.run()
    r = by_name(s)["b.mp4"]
    assert (r.status, r.stage, r.detail) == ("failed", "asr", "RuntimeError: boom")
    assert read_json(env.marker(b)) == {
        "path": str(b),
        "stage": "asr",
        "exception": "RuntimeError",
        "error": "RuntimeError: boom",
        "attempts": 1,
        "tapesift": __version__,
    }
    assert not (env.out / "assets" / asset_file_name(asset_id(b))).exists()
    assert asset_id(b) not in env.spy.upserts
    assert s.counts()["indexed"] == 5
    assert s.exit_code == 1

    # Run 2: retried, attempts 2.
    env.new_analyses()
    assert env.run().exit_code == 1
    assert env.new_analyses() == ["b.mp4"]
    assert read_json(env.marker(b))["attempts"] == 2

    # Run 3: the cap. Not analysed again.
    s = env.run()
    r = by_name(s)["b.mp4"]
    assert r.status == "failed_before"
    assert r.detail == f"failed before (2 attempts on {__version__}); not retried"
    assert env.new_analyses() == []
    assert s.exit_code == 1

    # Run 4: another tapesift version resets the count.
    m = read_json(env.marker(b))
    m["tapesift"] = "0.0.1"
    env.marker(b).write_text(json.dumps(m), encoding="utf-8")
    assert env.run().exit_code == 1
    assert env.new_analyses() == ["b.mp4"]
    assert read_json(env.marker(b))["attempts"] == 1

    # Run 5: success deletes the marker.
    env.faults(None)
    s = env.run()
    assert by_name(s)["b.mp4"].status == "indexed"
    assert not env.marker(b).exists()
    assert s.exit_code == 0


def test_marker_write_failure_does_not_stop_batch(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import tapesift.runner.run as run_mod

    real = run_mod._write_small_json  # pyright: ignore[reportPrivateUsage]

    def flaky(path: Path, obj: object) -> None:
        if path.parent.name == "failed":
            raise OSError("disk full")
        real(path, obj)

    monkeypatch.setattr(run_mod, "_write_small_json", flaky)
    env.six()
    env.faults("b.mp4:boom")
    with caplog.at_level(logging.INFO):
        s = env.run()
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].startswith("cannot write failed marker for ")
    assert statuses(s) == {n: ("failed" if n == "b.mp4" else "indexed") for n in NAMES}


def test_store_error_fails_asset(env: Env) -> None:
    paths = env.six()
    c = paths[2]
    env.spy.fail_on["c.mp4"] = RuntimeError("db")
    s = env.run()
    r = by_name(s)["c.mp4"]
    assert (r.status, r.stage) == ("failed", "store")
    assert env.marker(c).exists()
    assert not (env.out / "assets" / asset_file_name(asset_id(c))).exists()
    assert s.counts()["indexed"] == 5


def test_wall_clock_limit_kills_stuck_worker(env: Env) -> None:
    paths = env.six()
    env.faults("c.mp4:stuck")
    t0 = time.monotonic()
    s = env.run(limits=Limits(index_min_s=1.0, index_per_media_s=0.0))
    assert time.monotonic() - t0 < 120
    r = by_name(s)["c.mp4"]
    assert (r.status, r.stage) == ("failed", "asr")
    assert r.detail == "WorkerTimeout: timed out after 1 s"
    assert read_json(env.marker(paths[2]))["exception"] == "WorkerTimeout"
    assert [n for n in NAMES if statuses(s)[n] == "indexed"] == [
        "a.mp4",
        "b.mp4",
        "d.mp4",
        "e.mp4",
        "f.mp4",
    ]


def test_no_progress_limit_kills(env: Env) -> None:
    env.six()
    env.faults("c.mp4:stuck")
    t0 = time.monotonic()
    s = env.run(limits=Limits(stall_s=1.0))
    assert time.monotonic() - t0 < 120
    assert by_name(s)["c.mp4"].detail == "WorkerTimeout: no progress for 1 s"
    assert s.counts()["indexed"] == 5


def test_beats_keep_slow_file_alive(env: Env) -> None:
    env.six()
    env.faults("c.mp4:beating")
    s = env.run(limits=Limits(stall_s=1.0))
    assert s.counts()["indexed"] == 6


def test_worker_crash_fails_asset(env: Env) -> None:
    paths = env.six()
    env.faults("b.mp4:crash")
    s = env.run()
    assert by_name(s)["b.mp4"].detail == "WorkerCrashed: worker exited with code 3"
    assert read_json(env.marker(paths[1]))["exception"] == "WorkerCrashed"
    assert s.counts()["indexed"] == 5
    assert statuses(s)["c.mp4"] == "indexed"


@pytest.mark.parametrize(
    ("load", "message"),
    [
        (broken, "fake: no model"),
        (dies, "worker exited with code 3 while loading models"),
    ],
    ids=["load_error", "worker_dies_while_loading"],
)
def test_load_failures_are_model_load_errors(env: Env, load: Load, message: str) -> None:
    env.six()
    with pytest.raises(ModelLoadError) as e:
        env.run(load=load)
    assert str(e.value) == message
    assert env.assets == []
    assert env.markers() == []


def test_model_load_wait_is_bounded(env: Env) -> None:
    env.six()
    t0 = time.monotonic()
    with pytest.raises(ModelLoadError) as e:
        env.run(load=slowload, limits=Limits(load_s=1.0))
    assert str(e.value) == "models did not load within 1 s"
    assert time.monotonic() - t0 < 60


_DRIVER = """\
import sys
from pathlib import Path

from tapesift.config import Config
from tapesift.runner.run import run_index
from tests.runner_setups import SpyStore, quick

if __name__ == "__main__":
    spy = SpyStore()
    run_index([Path(sys.argv[1])], Config(out_dir=Path(sys.argv[2])), load=quick,
              open_store=lambda c: spy)
"""


def test_hard_kill_then_rerun_resumes_from_k(env: Env) -> None:
    paths = env.six()
    driver = env.root / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    env.faults("c.mp4:killparent")
    proc = subprocess.run(
        [sys.executable, str(driver), str(env.inp), str(env.out)],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        timeout=120,
    )
    assert proc.returncode == -9
    assert {p.name for p in env.assets} == {asset_file_name(asset_id(p)) for p in paths[:2]}
    pid = int(next(ln for ln in env.lines() if ln.startswith("pid:")).removeprefix("pid:"))
    deadline = time.monotonic() + 10
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break  # the parent-death watchdog ended the worker
        assert time.monotonic() < deadline, f"worker {pid} outlived its parent"
        time.sleep(0.1)

    env.faults(None)
    env.mark_seen()
    s = env.run()
    assert env.new_analyses() == ["c.mp4", "d.mp4", "e.mp4", "f.mp4"]
    assert len(env.assets) == 6
    assert statuses(s) == {
        "a.mp4": "skipped",
        "b.mp4": "skipped",
        "c.mp4": "indexed",
        "d.mp4": "indexed",
        "e.mp4": "indexed",
        "f.mp4": "indexed",
    }


def test_keyboard_interrupt_returns_partial_summary(env: Env) -> None:
    env.six()
    env.spy.fail_on["b.mp4"] = KeyboardInterrupt()
    s = env.run()
    assert s.interrupted_by == signal.SIGINT
    assert s.total == 6
    assert [(Path(r.path).name, r.status) for r in s.files] == [("a.mp4", "indexed")]
    assert len(env.assets) == 1
    assert env.markers() == []
    assert multiprocessing.active_children() == []


def test_signal_during_write_is_deferred(env: Env) -> None:
    class KillSelfStore(SpyStore):
        def upsert(self, record: Any) -> None:
            super().upsert(record)
            if Path(record.asset.path).name == "b.mp4":
                os.kill(os.getpid(), signal.SIGINT)

    env.six()
    env.spy = KillSelfStore()
    restore = install_interrupt_handlers()
    try:
        s = env.run()
    finally:
        restore()
    assert s.interrupted_by == signal.SIGINT
    assert [(Path(r.path).name, r.status) for r in s.files] == [
        ("a.mp4", "indexed"),
        ("b.mp4", "indexed"),
    ]
    assert len(env.assets) == 2
    assert len(env.spy.upserts) == 2


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_signal_stops_run_and_leaves_resumable_state(env: Env, sig: signal.Signals) -> None:
    env.six()
    env.faults("b.mp4:slow")
    main = threading.get_ident()

    def fire() -> None:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not env.assets:
            time.sleep(0.05)
        signal.pthread_kill(main, sig)  # to this process's main thread, like a terminal would

    saved = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    restore = install_interrupt_handlers()
    timer = threading.Thread(target=fire, daemon=True)
    t0 = time.monotonic()
    try:
        timer.start()
        s = env.run()
    finally:
        restore()
        timer.join(timeout=100)
    assert time.monotonic() - t0 < 120
    assert s.interrupted_by == sig
    assert len(env.assets) == 1
    assert env.markers() == []
    assert list(env.out.rglob(".tapesift-*.tmp")) == []
    assert {x: signal.getsignal(x) for x in saved} == saved
    assert multiprocessing.active_children() == []


def test_duplicate_confirmed_by_full_hash(env: Env) -> None:
    clean = env.put("clean.mp4", "clean.mp4")
    env.put("clean_copy.mp4", "clean_copy.mp4")
    s = env.run()
    r = by_name(s)
    assert r["clean.mp4"].status == "indexed"
    assert r["clean_copy.mp4"].status == "duplicate"
    assert r["clean_copy.mp4"].code == WarningCode.DUPLICATE
    assert r["clean_copy.mp4"].detail == f"same content as {clean}"
    assert len(env.assets) == 1


def _write_wav(path: Path, seed: int) -> None:
    """16 kHz mono s16, 17 MiB of data. The file's first and last 8 MiB are identical for every
    seed; the 1 MiB at file offset 8 MiB (past the 44-byte header) is seeded noise."""
    data = bytearray(17 * MiB)
    noise = np.random.default_rng(seed).integers(0, 256, size=MiB, dtype=np.uint8)
    data[8 * MiB - 44 : 9 * MiB - 44] = noise.tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(bytes(data))


def test_tsid1_collision_indexes_both(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    p1, p2 = env.inp / "w1.wav", env.inp / "w2.wav"
    _write_wav(p1, 1)
    _write_wav(p2, 2)
    assert asset_id(p1) == asset_id(p2)
    assert asset_id(p1, full=True) != asset_id(p2, full=True)
    with caplog.at_level(logging.INFO):
        s = env.run()
    r = by_name(s)
    assert (r["w1.wav"].status, r["w1.wav"].asset_id) == ("indexed", asset_id(p1))
    assert (r["w2.wav"].status, r["w2.wav"].asset_id) == ("indexed", asset_id(p2, full=True))
    assert len(env.assets) == 2
    warns = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and r.getMessage().startswith("tsid1 collision: ")
    ]
    assert len(warns) == 1
    assert str(p1) in warns[0]
    assert str(p2) in warns[0]

    env.new_analyses()
    s = env.run()
    assert statuses(s) == {"w1.wav": "skipped", "w2.wav": "skipped"}
    assert env.new_analyses() == []


def test_id_mode_mismatch_refused(env: Env) -> None:
    env.six()
    env.run()
    before = snapshot(env.out)
    with pytest.raises(OutDirError) as e:
        env.run(full_hash=True)
    assert str(e.value) == (
        f"{env.out} is a tsid1 index; this run uses sha256 IDs. "
        "Rerun without --full-hash, or use another --out."
    )
    assert snapshot(env.out) == before


def test_max_media_hours_defers_rest(env: Env) -> None:
    env.six()
    s = env.run(max_media_hours=0.001)  # 3.6 s; clean.mp4 is 5 s
    r = by_name(s)
    assert r["a.mp4"].status == "indexed"
    for n in NAMES[1:]:
        assert (r[n].status, r[n].asset_id) == ("deferred", None)
    assert s.exit_code == 0
    assert env.new_analyses() == ["a.mp4"]

    s = env.run()
    assert statuses(s) == {n: ("skipped" if n == "a.mp4" else "indexed") for n in NAMES}


def test_dry_run_writes_nothing(env: Env) -> None:
    paths = env.six()
    s = env.run(dry=True)
    assert s.counts()["pending"] == 6
    assert not env.out.exists()
    assert not any(ln.startswith("pid:") for ln in env.lines())  # load never ran

    env.run([paths[0], paths[1]])
    s = env.run(dry=True)
    assert statuses(s) == {n: ("skipped" if n in ("a.mp4", "b.mp4") else "pending") for n in NAMES}


def test_changed_file_replaces_old_record(env: Env) -> None:
    x = env.put("x.mp4", "clean.mp4")
    old = asset_id(x)
    assert env.run().counts()["indexed"] == 1
    shutil.copyfile(FIXTURES / "speech.mp4", x)
    new = asset_id(x)
    assert new != old
    s = env.run()
    assert (by_name(s)["x.mp4"].status, by_name(s)["x.mp4"].asset_id) == ("indexed", new)
    assert env.spy.deletes == [old]
    assert not (env.out / "assets" / asset_file_name(old)).exists()
    assert (env.out / "assets" / asset_file_name(new)).exists()


def test_moved_file_is_skipped(env: Env) -> None:
    a = env.put("a.mp4")
    env.run()
    env.new_analyses()
    (env.inp / "sub").mkdir()
    a.rename(env.inp / "sub" / "a.mp4")
    s = env.run()
    r = by_name(s)["a.mp4"]
    assert (r.status, r.detail) == ("skipped", f"already indexed as {a}")
    assert env.new_analyses() == []
    assert len(env.spy.upserts) == 1


def test_sigterm_during_respawn_stops_the_run(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    from multiprocessing.process import BaseProcess

    real_start = BaseProcess.start
    starts: list[int] = []

    def start(self: BaseProcess) -> None:
        starts.append(1)
        if len(starts) == 2:  # the respawn after b's worker crashed
            os.kill(os.getpid(), signal.SIGTERM)
        real_start(self)

    monkeypatch.setattr(BaseProcess, "start", start)
    env.six()
    env.faults("b.mp4:crash")
    restore = install_interrupt_handlers()
    try:
        s = env.run()
    finally:
        restore()
    assert s.interrupted_by == signal.SIGTERM
    assert [(Path(r.path).name, r.status) for r in s.files] == [
        ("a.mp4", "indexed"),
        ("b.mp4", "failed"),
    ]
    assert multiprocessing.active_children() == []


def test_unreadable_indexed_file_is_not_a_match(env: Env) -> None:
    p = env.put("copy.mp4", "clean_copy.mp4")
    folder = env.root / "gone"  # an indexed "file" that can't be hashed
    folder.mkdir()
    aid = asset_id(p)
    (env.out / "assets").mkdir(parents=True)
    doc = {"asset": {"id": aid, "path": str(folder)}}
    (env.out / "assets" / asset_file_name(aid)).write_text(json.dumps(doc), encoding="utf-8")
    s = env.run()
    r = by_name(s)["copy.mp4"]
    assert (r.status, r.asset_id) == ("indexed", asset_id(p, full=True))


def test_deferral_keeps_walk_failures(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    import tapesift.runner.run as run_mod

    real_walk = run_mod.walk
    bad = FileResult("/x/bad.mp4", "failed", None, None, WarningCode.UNREADABLE, None, "why")

    def walk(paths: Any, exclude: Any = None) -> Any:
        return [*real_walk(paths, exclude), bad]

    monkeypatch.setattr(run_mod, "walk", walk)
    env.six()
    s = env.run(max_media_hours=0.001)
    assert s.files[-1] == bad
    assert [r.status for r in s.files[:-1]] == ["indexed"] + ["deferred"] * 5
