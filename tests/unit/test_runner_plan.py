"""E7 runner v0, pure parts (docs/specs/30-runner.md, test_runner_plan.py). No worker process."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import signal
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tapesift.runner.report import STATUSES, FileResult, Status, Summary, render, to_dict
from tapesift.runner.run import (
    ASSET_FILE_RE,
    INDEX_FILE,
    Limits,
    Marker,
    OutDirError,
    _write_small_json,  # pyright: ignore[reportPrivateUsage]
    asset_file_name,
    exit_on_next_signal,
    next_attempts,
    open_out_dir,
    read_marker,
    retry_allowed,
    scan_assets,
    walk,
)
from tapesift.warning_codes import WarningCode

V = "0.1.0"
HEX = "ab" * 32


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def _marker(**over: Any) -> Marker:
    m: dict[str, Any] = {
        "path": "/in/b.mp4",
        "stage": "asr",
        "exception": "RuntimeError",
        "error": "RuntimeError: boom",
        "attempts": 1,
        "tapesift": V,
    }
    m.update(over)
    return m  # pyright: ignore[reportReturnType]


# --- walk ---------------------------------------------------------------------------------


def test_walk_order(tmp_path: Path) -> None:
    root = tmp_path / "in"
    for name in ("b/z.mp4", "a/y.mp4", "B.mp4", "é.mp4", "a.mp4"):
        _touch(root / name)
    assert walk([root]) == [
        root / "B.mp4",
        root / "a.mp4",
        root / "é.mp4",
        root / "a" / "y.mp4",
        root / "b" / "z.mp4",
    ]
    assert walk([root / "b", root / "a"]) == [root / "b" / "z.mp4", root / "a" / "y.mp4"]


def test_walk_skips_hidden_and_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    root = tmp_path / "in"
    for name in ("a.mp4", ".DS_Store", "._a.mp4", ".cache/x.mp4"):
        _touch(root / name)
    with caplog.at_level(logging.INFO):
        assert walk([root]) == [root / "a.mp4"]
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("skipping hidden")]
    assert sorted(lines) == sorted(
        f"skipping hidden {root / n}" for n in (".DS_Store", "._a.mp4", ".cache")
    )
    assert walk([root / ".DS_Store"]) == [root / ".DS_Store"]  # a named PATH is never skipped


def test_walk_skips_the_index_folder(tmp_path: Path) -> None:
    root = tmp_path / "in"
    for name in ("a.mp4", "out/assets/x.json", "out/index.json", "sub/b.mp4"):
        _touch(root / name)
    assert walk([root], exclude=root / "out") == [root / "a.mp4", root / "sub" / "b.mp4"]
    assert walk([root / "out"], exclude=root / "out") == []  # the index itself as input


def test_walk_rejects_undecodable_name() -> None:
    assert walk([Path("/x/bad\udcff.mp4")]) == [
        FileResult(
            "/x/bad\\xff.mp4",
            "failed",
            None,
            None,
            WarningCode.UNREADABLE,
            None,
            "file name is not valid UTF-8",
        )
    ]


# --- markers and retry cap ----------------------------------------------------------------


@pytest.mark.parametrize("case", ["valid", "unparsable", "wrong_shape"])
def test_read_marker(case: str, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    p = tmp_path / asset_file_name("tsid1:" + HEX)
    assert read_marker(p) is None  # missing: None, silently
    assert not caplog.records
    if case == "valid":
        m = _marker()
        p.write_text(json.dumps(m), encoding="utf-8")
        assert read_marker(p) == m
        assert not caplog.records
        return
    if case == "unparsable":
        p.write_bytes(b"{")
    else:
        p.write_text(json.dumps(_marker(attempts="2")), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read_marker(p) is None
    assert [r.getMessage() for r in caplog.records] == [f"ignoring malformed marker {p.name}"]


def test_retry_allowed() -> None:
    assert retry_allowed(None, V) is True
    assert retry_allowed(_marker(attempts=1), V) is True
    assert retry_allowed(_marker(attempts=2), V) is False
    assert retry_allowed(_marker(attempts=2, tapesift="0.0.1"), V) is True


def test_next_attempts() -> None:
    assert next_attempts(None, V) == 1
    assert next_attempts(_marker(attempts=1), V) == 2
    assert next_attempts(_marker(attempts=2, tapesift="0.0.1"), V) == 1


def test_small_json_write_failure_keeps_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "index.json"
    _write_small_json(p, {"layout": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"layout": 1}
    assert [f.name for f in tmp_path.iterdir()] == ["index.json"]  # no .tapesift-*.tmp

    old = p.read_bytes()

    def boom(src: object, dst: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="replace failed"):
        _write_small_json(p, {"layout": 2})
    assert p.read_bytes() == old
    assert [f.name for f in tmp_path.iterdir()] == ["index.json"]


# --- limits -------------------------------------------------------------------------------


def test_limits() -> None:
    lim = Limits()
    assert lim.probe_deadline(0, full=False) == 120.0
    assert lim.probe_deadline(100 * 2**20, full=True) == 130.0
    assert lim.index_deadline(None) == 43200.0
    assert lim.index_deadline(10.0) == 650.0
    assert lim.index_deadline(10800.0) == 43200.0  # a 3 h file gets 12 h, not 30 h


@given(
    d1=st.floats(min_value=0, max_value=1e7),
    d2=st.floats(min_value=0, max_value=1e7),
    size=st.integers(min_value=0, max_value=2**40),
)
def test_limits_properties(d1: float, d2: float, size: int) -> None:
    lim = Limits()
    lo, hi = sorted((d1, d2))
    assert lim.index_deadline(lo) <= lim.index_deadline(hi) <= lim.index_max_s
    assert lim.index_deadline(lo) >= min(lim.index_min_s, lim.index_max_s)
    assert lim.probe_deadline(size, full=False) == lim.probe_s
    assert lim.probe_deadline(size, full=True) >= lim.probe_deadline(size, full=False)


# --- out dir ------------------------------------------------------------------------------


def test_open_out_dir_fresh(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with open_out_dir(out, "tsid1", create=True):
        assert (out / "assets").is_dir()
        assert (out / "failed").is_dir()
        assert (out / ".lock").exists()
    assert json.loads((out / INDEX_FILE).read_text(encoding="utf-8")) == {
        "layout": 1,
        "id_mode": "tsid1",
    }


def test_open_out_dir_same_mode_removes_stale_temp_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with open_out_dir(out, "tsid1", create=True):
        pass
    stale = [out / ".tapesift-5.tmp", out / "assets" / ".tapesift-123.tmp"]
    stale.append(out / "failed" / ".tapesift-9.tmp")
    for f in stale:
        f.write_bytes(b"x")
    keep = _touch(out / "assets" / asset_file_name("tsid1:" + HEX))
    with open_out_dir(out, "tsid1", create=True):
        pass
    assert not any(f.exists() for f in stale)
    assert keep.exists()


def test_open_out_dir_other_mode(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with open_out_dir(out, "tsid1", create=True):
        pass
    with pytest.raises(OutDirError) as e, open_out_dir(out, "sha256", create=True):
        pass
    assert str(e.value) == (
        f"{out} is a tsid1 index; this run uses sha256 IDs. "
        "Rerun without --full-hash, or use another --out."
    )


def test_open_out_dir_busy(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with open_out_dir(out, "tsid1", create=True):
        pass
    fd = os.open(out / ".lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(OutDirError) as e, open_out_dir(out, "tsid1", create=True):
            pass
        assert str(e.value) == f"{out} is in use by another tapesift index run"
    finally:
        os.close(fd)


def test_open_out_dir_dry_missing_creates_nothing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with open_out_dir(out, "tsid1", create=False):
        pass
    assert not out.exists()


# --- asset files --------------------------------------------------------------------------


def test_asset_file_name() -> None:
    for scheme in ("tsid1", "sha256"):
        name = asset_file_name(f"{scheme}:{HEX}")
        assert name == f"{scheme}_{HEX}.json"
        assert ASSET_FILE_RE.fullmatch(name)


def test_scan_assets(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    x, y = "tsid1:" + "11" * 32, "sha256:" + "22" * 32
    for aid, p in ((x, "/in/x.mp4"), (y, "/in/y é.mp4")):
        doc = {"asset": {"id": aid, "path": p}}
        (assets / asset_file_name(aid)).write_text(json.dumps(doc), encoding="utf-8")
    trunc = assets / asset_file_name("tsid1:" + "33" * 32)
    trunc.write_text('{"asset": {"id": "tsid1:', encoding="utf-8")
    wrong = assets / asset_file_name("tsid1:" + "44" * 32)
    wrong.write_text(json.dumps({"asset": {"id": x, "path": "/in/z.mp4"}}), encoding="utf-8")
    (assets / ".x.json").write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert scan_assets(assets) == {x: "/in/x.mp4", y: "/in/y é.mp4"}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert f"ignoring unreadable {trunc.name}: JSONDecodeError" in warnings
    assert any(wrong.name in w for w in warnings)
    assert scan_assets(tmp_path / "missing") == {}


# --- report -------------------------------------------------------------------------------


def _summary(*files: FileResult, **over: Any) -> Summary:
    kw: dict[str, Any] = {
        "out_dir": "/out",
        "id_mode": "tsid1",
        "dry_run": False,
        "interrupted_by": None,
        "max_media_hours": None,
        "total": len(files),
        "files": files,
    }
    kw.update(over)
    return Summary(**kw)


def _fr(name: str, status: Status, dur: float | None = 1.0, **kw: Any) -> FileResult:
    aid = None if status == "deferred" else "tsid1:" + name[0].encode().hex() * 32
    return FileResult(f"/in/{name}", status, aid, dur, **kw)


def test_exit_code() -> None:
    def code(*statuses: Status) -> int:
        return _summary(*(_fr(f"{i}.mp4", s) for i, s in enumerate(statuses))).exit_code

    assert code("indexed") == 0
    assert code("indexed", "failed") == 1
    assert code("failed_before") == 1
    assert code("duplicate", "skipped") == 0
    assert code("deferred") == 0


@given(
    items=st.lists(
        st.tuples(
            st.sampled_from(STATUSES),
            st.one_of(st.none(), st.floats(min_value=0, max_value=1e6)),
        ),
        max_size=30,
    ),
    dry=st.booleans(),
)
def test_counts_and_media_hours(items: list[tuple[Status, float | None]], dry: bool) -> None:
    s = _summary(*(_fr(f"{i}.mp4", st_, d) for i, (st_, d) in enumerate(items)), dry_run=dry)
    counts = s.counts()
    assert list(counts) == list(STATUSES)
    assert sum(counts.values()) == len(items)
    counted = "pending" if dry else "indexed"
    want = sum(d or 0.0 for st_, d in items if st_ == counted) / 3600
    assert s.media_hours() == pytest.approx(want)


def test_to_dict_exact() -> None:
    a, b, c, d, e, f, g = (f"{ch}.mp4" for ch in "abcdefg")
    s = _summary(
        _fr(a, "indexed", 1234.5678),
        _fr(b, "pending", 1800.0),
        _fr(c, "skipped", 10.0, detail="already indexed as /old/c.mp4"),
        _fr(d, "duplicate", 7.0, code=WarningCode.DUPLICATE, detail="same content as /in/a.mp4"),
        _fr(e, "failed", 3.0, stage="asr", detail="RuntimeError: boom"),
        _fr(f, "failed_before", 3.0, stage="asr", detail="failed before (2 attempts on 0.1.0)"),
        _fr(g, "deferred"),
        max_media_hours=2.5,
    )

    def entry(name: str, status: str, **kw: Any) -> dict[str, Any]:
        aid = None if status == "deferred" else "tsid1:" + name[0].encode().hex() * 32
        base = {"path": f"/in/{name}", "status": status, "asset_id": aid}
        return base | {"code": None, "stage": None, "detail": None} | kw

    expected: dict[str, Any] = {
        "version": 1,
        "out_dir": "/out",
        "id_mode": "tsid1",
        "dry_run": False,
        "interrupted": False,
        "max_media_hours": 2.5,
        "total": 7,
        "counts": dict.fromkeys(STATUSES, 1),
        "media_hours": 0.3429,
        "files": [
            entry(a, "indexed"),
            entry(b, "pending"),
            entry(c, "skipped", detail="already indexed as /old/c.mp4"),
            entry(d, "duplicate", code="DUPLICATE", detail="same content as /in/a.mp4"),
            entry(e, "failed", stage="asr", detail="RuntimeError: boom"),
            entry(f, "failed_before", stage="asr", detail="failed before (2 attempts on 0.1.0)"),
            entry(g, "deferred"),
        ],
    }
    got = to_dict(s)
    assert list(got) == list(expected)
    assert list(cast("dict[str, int]", got["counts"])) == list(STATUSES)
    assert got == expected
    assert json.loads(json.dumps(got)) == expected  # code is a plain string


def test_render_normal() -> None:
    s = _summary(
        _fr("a.mp4", "indexed", 2700.0),
        _fr("b.mp4", "indexed", 2700.0),
        _fr("c.mp4", "skipped"),
        _fr("d.mp4", "duplicate", code=WarningCode.DUPLICATE, detail="same content as /in/a.mp4"),
        _fr("e.mp4", "failed", stage="asr", detail="RuntimeError: boom"),
        FileResult(
            "/in/x.txt",
            "failed",
            None,
            None,
            WarningCode.UNREADABLE,
            None,
            "InvalidDataError: Invalid data found when processing input",
        ),
        _fr("f.mp4", "failed_before", stage="asr", detail="failed before (2 attempts on 0.1.0)"),
    )
    assert render(s) == "\n".join(
        [
            "indexed 2, skipped 1, duplicate 1, failed 2, failed before 1, deferred 0"
            " (7 files, 1.50 h of media)",
            "failed:",
            "  /in/e.mp4 (asr): RuntimeError: boom",
            "  /in/x.txt: UNREADABLE InvalidDataError: Invalid data found when processing input",
            "failed before:",
            "  /in/f.mp4 (asr): failed before (2 attempts on 0.1.0)",
            "  to retry, delete their markers in /out/failed/",
            "duplicate:",
            "  /in/d.mp4: DUPLICATE same content as /in/a.mp4",
        ]
    )


def test_render_dry_run() -> None:
    s = _summary(
        _fr("a.mp4", "pending", 1800.0),
        _fr("b.mp4", "pending", 1800.0),
        _fr("c.mp4", "skipped"),
        _fr("d.mp4", "duplicate", code=WarningCode.DUPLICATE, detail="same content as /in/a.mp4"),
        dry_run=True,
    )
    assert render(s) == "\n".join(
        [
            "dry run, nothing written: 2 to index (1.00 h of media), skipped 1, duplicate 1,"
            " failed 0, failed before 0, deferred 0 (4 files)",
            "duplicate:",
            "  /in/d.mp4: DUPLICATE same content as /in/a.mp4",
        ]
    )


def test_render_interrupted_and_deferred() -> None:
    s = _summary(
        _fr("a.mp4", "indexed", 1800.0),
        _fr("b.mp4", "deferred"),
        _fr("c.mp4", "deferred"),
        total=5,
        max_media_hours=0.5,
        interrupted_by=signal.SIGINT,
    )
    assert render(s) == "\n".join(
        [
            "indexed 1, skipped 0, duplicate 0, failed 0, failed before 0, deferred 2"
            " (5 files, 0.50 h of media)",
            "stopped by --max-media-hours 0.5: 2 files left for the next run",
            "interrupted by SIGINT after 3 of 5 files; rerun to resume",
        ]
    )


# --- signals ------------------------------------------------------------------------------


def test_second_signal_exits_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    exits: list[int] = []
    monkeypatch.setattr(os, "_exit", exits.append)
    sigs = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    before = {s: signal.getsignal(s) for s in sigs}
    try:
        exit_on_next_signal(signal.SIGTERM)
        signal.raise_signal(signal.SIGINT)
        assert exits == [143]
    finally:
        for s, h in before.items():
            signal.signal(s, h)
