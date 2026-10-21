"""`tapesift index` end to end on the fixtures (docs/specs/30-runner.md, test_index_fixtures.py):
the CLI through typer's CliRunner, with the real probe, PyAVDecoder, E3, E4 and E5. Every model is a
fake (ADR 0008): `pi.load` is `fake_pipeline` and the store is a MemoryStore or a LanceStore over
FakeEmbedder."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from tests.fakes import FakeEmbedder, MemoryStore
from tests.runner_setups import SPY_ENV, broken, fake_pipeline
from tests.smoke.conftest import FIXTURES
from typer.testing import CliRunner

from tapesift.cli import app
from tapesift.store import lance
from tapesift.store.lance import LanceStore, StoreError

# isort: split
import tapesift.pipeline.index as pi

CLEAN_COPY_DETAIL = f"same content as {FIXTURES.absolute() / 'clean.mp4'}"
INVALID = "InvalidDataError: Invalid data found when processing input"
SCHEMA = json.loads(
    files("tapesift.schema").joinpath("asset-1.0.schema.json").read_text(encoding="utf-8")
)
runner = CliRunner()


@dataclass
class FixtureRun:
    out: Path
    spy_file: Path
    exit_code: int
    doc: dict[str, Any]

    def analyses(self) -> list[str]:
        lines = self.spy_file.read_text(encoding="utf-8").splitlines()
        return [ln for ln in lines if not ln.startswith("pid:")]


def by_name(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {Path(r["path"]).name: r for r in doc["files"]}


def make_in(root: Path, *names: str) -> Path:
    inp = root / "in"
    inp.mkdir()
    for n in names:
        shutil.copyfile(FIXTURES / n, inp / n)
    return inp


@pytest.fixture(scope="module", autouse=True)
def fakes(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Module-scoped patches. Returns the spy file the workers append to."""
    spy = tmp_path_factory.mktemp("spy") / "spy.txt"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pi, "load", fake_pipeline)
        mp.setattr(pi, "open_store", lambda c: MemoryStore(FakeEmbedder()))
        mp.setattr(pi, "vision_available", lambda: True)
        mp.setenv(SPY_ENV, str(spy))
        yield spy


@pytest.fixture(scope="module")
def fixture_run(fakes: Path, tmp_path_factory: pytest.TempPathFactory) -> FixtureRun:
    out = tmp_path_factory.mktemp("fixtures_out") / "out"
    r = runner.invoke(app, ["index", str(FIXTURES), "--out", str(out), "--json"])
    assert r.stdout, f"no --json on stdout: exit {r.exit_code}, {r.exception!r}, {r.stderr}"
    return FixtureRun(out, fakes, r.exit_code, json.loads(r.stdout))


def test_only_unreadable_files_fail(fixture_run: FixtureRun) -> None:
    doc, files_ = fixture_run.doc, by_name(fixture_run.doc)
    assert fixture_run.exit_code == 1
    assert doc["total"] == 26
    failed = {n: r for n, r in files_.items() if r["status"] == "failed"}
    assert set(failed) == {"not_media.txt", "manifest.json"}
    for r in failed.values():
        assert r["code"] == "UNREADABLE"
    assert failed["not_media.txt"]["detail"] == INVALID
    assert failed["manifest.json"]["detail"] == INVALID  # observed with probe() on 2026-10-21
    dups = {n: r for n, r in files_.items() if r["status"] == "duplicate"}
    assert set(dups) == {"clean_copy.mp4"}
    assert dups["clean_copy.mp4"]["code"] == "DUPLICATE"
    assert dups["clean_copy.mp4"]["detail"] == CLEAN_COPY_DETAIL
    assert doc["counts"] == {
        "indexed": 23,
        "pending": 0,
        "skipped": 0,
        "duplicate": 1,
        "failed": 2,
        "failed_before": 0,
        "deferred": 0,
    }
    assert files_["truncated.mp4"]["status"] == "indexed"
    assert files_["unknown_codec.mov"]["status"] == "indexed"


def test_every_json_validates(fixture_run: FixtureRun) -> None:
    v = Draft202012Validator(SCHEMA)
    docs = sorted((fixture_run.out / "assets").glob("*.json"))
    assert len(docs) == 23
    for p in docs:
        v.validate(json.loads(p.read_text(encoding="utf-8")))


def test_rerun_indexes_nothing(fixture_run: FixtureRun) -> None:
    before = fixture_run.analyses()
    r = runner.invoke(app, ["index", str(FIXTURES), "--out", str(fixture_run.out), "--json"])
    assert r.exit_code == 1
    counts = json.loads(r.stdout)["counts"]
    assert (counts["skipped"], counts["duplicate"], counts["failed"]) == (23, 1, 2)
    assert counts["indexed"] == 0
    assert fixture_run.analyses() == before


def test_human_summary_on_stderr(tmp_path: Path) -> None:
    inp = make_in(tmp_path, "clean.mp4", "clean_copy.mp4", "not_media.txt")
    r = runner.invoke(app, ["index", str(inp), "--out", str(tmp_path / "out")])
    assert r.exit_code == 1
    assert r.stdout == ""
    assert (
        "indexed 1, skipped 0, duplicate 1, failed 1, failed before 0, deferred 0 (3 files,"
        in r.stderr
    )
    lines = r.stderr.splitlines()
    assert "failed:" in lines
    assert "duplicate:" in lines


def test_id_mode_mismatch_exits_2(tmp_path: Path) -> None:
    inp = make_in(tmp_path, "clean.mp4")
    out = tmp_path / "out"
    assert runner.invoke(app, ["index", str(inp), "--out", str(out)]).exit_code == 0
    r = runner.invoke(app, ["index", str(inp), "--out", str(out), "--full-hash"])
    assert r.exit_code == 2
    msg = (
        f"{out} is a tsid1 index; this run uses sha256 IDs. "
        "Rerun without --full-hash, or use another --out."
    )
    assert f"error: {msg}" in r.stderr.splitlines()


def test_store_error_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_store(cfg: Any) -> Any:
        raise StoreError("x: not a tapesift store")

    monkeypatch.setattr(pi, "open_store", bad_store)
    inp = make_in(tmp_path, "clean.mp4")
    r = runner.invoke(app, ["index", str(inp), "--out", str(tmp_path / "out")])
    assert r.exit_code == 2
    assert "error: x: not a tapesift store" in r.stderr.splitlines()


def test_model_load_error_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pi, "load", broken)
    inp = make_in(tmp_path, "clean.mp4")
    r = runner.invoke(app, ["index", str(inp), "--out", str(tmp_path / "out")])
    assert r.exit_code == 3
    assert "error: fake: no model" in r.stderr.splitlines()


def test_dry_run_json(tmp_path: Path) -> None:
    inp = make_in(tmp_path, "clean.mp4", "not_media.txt")
    out = tmp_path / "out"
    r = runner.invoke(app, ["index", str(inp), "--out", str(out), "--dry-run", "--json"])
    assert r.exit_code == 1
    doc = json.loads(r.stdout)
    assert doc["dry_run"] is True
    assert doc["counts"]["pending"] == 1
    assert doc["counts"]["failed"] == 1
    assert not out.exists()


def test_python_dash_m_spawns_cleanly(tmp_path: Path) -> None:
    """Without the __main__.py guard the spawned worker re-runs the CLI and this fails."""
    cmd = [sys.executable, "-m", "tapesift", "index", str(FIXTURES / "clean.mp4")]
    cmd += ["--out", str(tmp_path / "out"), "--dry-run", "--json"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["counts"]["pending"] == 1


def test_index_then_search_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inp = make_in(tmp_path, "speech.mp4", "clean.mp4")
    out = tmp_path / "out"
    monkeypatch.setattr(pi, "open_store", lambda c: LanceStore(c, FakeEmbedder()))
    r = runner.invoke(app, ["index", str(inp), "--out", str(out), "--json"])
    assert r.exit_code == 0, r.stderr
    assert json.loads(r.stdout)["counts"]["indexed"] == 2

    monkeypatch.setattr(lance, "load_embedder", FakeEmbedder)
    r = runner.invoke(app, ["search", "fake speech", "--out", str(out), "--json"])
    assert r.exit_code == 0, r.stderr
    hits = json.loads(r.stdout)["hits"]
    assert any(h["path"] == str(inp / "speech.mp4") for h in hits)
