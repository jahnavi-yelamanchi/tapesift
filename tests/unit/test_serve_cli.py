"""`tapesift serve` command (docs/specs/40-web-ui.md, Acceptance tests 17-24). The backend modules
that belong to other branches (store.lance, vision.embed, runner.run) are replaced in sys.modules by
fakes, so nothing real is imported or loaded (ADR 0008)."""

import importlib
import logging
import socket
import subprocess
import sys
import types
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tapesift.cli import ExitCode, app
from tapesift.config import Config, ModelLoadError

# isort: split
from tests.fakes import FakeEmbedder, MemoryStore

runner = CliRunner()
ANY_HOST = "0.0.0.0"  # noqa: S104  (the non-loopback case under test; nothing listens on it)

# `from tapesift.cli.serve import serve` in tapesift.cli makes the attribute tapesift.cli.serve the
# function, so the module is fetched from sys.modules, never by attribute or dotted string.
serve_mod = importlib.import_module("tapesift.cli.serve")


class FakeStoreError(Exception):
    pass


@dataclass
class Backends:
    store_error: type[Exception] = FakeStoreError
    embedder_error: Exception | None = None
    store_raises: Exception | None = None
    embedder_calls: list[Config] = field(default_factory=list)
    store_calls: int = 0
    scan_dirs: list[Path] = field(default_factory=list)
    runs: list[tuple[Any, tuple[Any, ...], int]] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)


@pytest.fixture
def be(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Backends:
    b = Backends()
    monkeypatch.chdir(tmp_path)  # no stray ./tapesift.toml

    def onnx_embedder(cfg: Config) -> FakeEmbedder:
        b.embedder_calls.append(cfg)
        if b.embedder_error is not None:
            raise b.embedder_error
        return FakeEmbedder()

    def lance_store(cfg: Config, embedder: Any) -> MemoryStore:
        b.store_calls += 1
        if b.store_raises is not None:
            raise b.store_raises
        return MemoryStore(FakeEmbedder())

    def scan_assets(assets_dir: Path) -> dict[str, str]:
        b.scan_dirs.append(assets_dir)
        return {}

    def fake_run(app_: Any, sock: socket.socket) -> None:
        b.runs.append((app_, sock.getsockname(), sock.family))
        sock.close()

    for name, attrs in {
        "tapesift.store.lance": {"LanceStore": lance_store, "StoreError": FakeStoreError},
        "tapesift.vision.embed": {"OnnxEmbedder": onnx_embedder},
        "tapesift.runner.run": {"scan_assets": scan_assets},
    }.items():
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(serve_mod, "_run", fake_run)
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: b.opened.append(url) or True)
    return b


def _index(tmp_path: Path) -> Path:
    out = tmp_path / "idx"
    (out / "store").mkdir(parents=True)
    return out


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _spy_allowed_hosts(monkeypatch: pytest.MonkeyPatch) -> list[Sequence[str]]:
    """Wrap tapesift.serve.app.create_app; return the allowed_hosts it was given."""
    appmod = importlib.import_module("tapesift.serve.app")
    real: Callable[..., Any] = appmod.create_app
    seen: list[Sequence[str]] = []

    def spy(store: Any, scan: Any, *, allowed_hosts: Sequence[str]) -> Any:
        seen.append(list(allowed_hosts))
        return real(store, scan, allowed_hosts=allowed_hosts)

    monkeypatch.setattr(appmod, "create_app", spy)
    return seen


def _lines(text: str) -> list[str]:
    return text.splitlines()


# 17
def test_missing_extra_exits_3(be: Backends, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serve_mod, "serve_available", lambda: False)
    r = runner.invoke(app, ["serve"])
    assert r.exit_code == ExitCode.ENVIRONMENT
    assert 'error: tapesift serve needs the serve extra: install "tapesift[serve]"' in _lines(
        r.stderr
    )
    assert be.runs == []


# 18
def test_no_index_exits_2_before_model_load(be: Backends, tmp_path: Path) -> None:
    out = tmp_path / "empty"
    out.mkdir()
    r = runner.invoke(app, ["serve", "--out", str(out)])
    assert r.exit_code == ExitCode.BAD_INPUT
    msg = f'error: no index at {out}: run "tapesift index" first, or pass --out'
    assert msg in _lines(r.stderr)
    assert be.embedder_calls == []
    assert be.store_calls == 0
    assert not (out / "store").exists()


# 19
def test_bad_config_exits_2(be: Backends, tmp_path: Path) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text("colour = 1\n", encoding="utf-8")
    r = runner.invoke(app, ["serve", "--config", str(cfg), "--out", str(_index(tmp_path))])
    assert r.exit_code == ExitCode.BAD_INPUT
    assert "colour: Extra inputs are not permitted" in r.stderr
    assert be.embedder_calls == []


# 20
@pytest.mark.parametrize("which", ["model", "store"])
def test_backend_errors(be: Backends, tmp_path: Path, which: str) -> None:
    if which == "model":
        be.embedder_error = ModelLoadError("x")
        code, msg = ExitCode.ENVIRONMENT, "error: x"
    else:
        be.store_raises = be.store_error("y")
        code, msg = ExitCode.BAD_INPUT, "error: y"
    r = runner.invoke(app, ["serve", "--out", str(_index(tmp_path))])
    assert r.exit_code == code
    assert msg in _lines(r.stderr)
    assert be.runs == []


# 21
def test_port_in_use_exits_2(be: Backends, tmp_path: Path) -> None:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        r = runner.invoke(app, ["serve", "--out", str(_index(tmp_path)), "--port", str(port)])
    assert r.exit_code == ExitCode.BAD_INPUT
    assert r.stderr.startswith(f"error: cannot listen on 127.0.0.1:{port}:")
    assert be.runs == []


# 22
def test_loopback_default(
    be: Backends, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The port is passed (8765 may be busy on a dev machine); the host is left at its default.
    assert serve_mod.DEFAULT_HOST == "127.0.0.1"
    assert serve_mod.DEFAULT_PORT == 8765
    hosts = _spy_allowed_hosts(monkeypatch)
    port = _free_port()
    with caplog.at_level(logging.WARNING):
        r = runner.invoke(app, ["serve", "--out", str(_index(tmp_path)), "--port", str(port)])
    assert r.exit_code == ExitCode.OK, r.stderr
    assert len(be.runs) == 1
    _, (addr, bound_port, *_), family = be.runs[0]
    assert (addr, bound_port, family) == ("127.0.0.1", port, socket.AF_INET)
    assert hosts == [["127.0.0.1", "[::1]", "localhost"]]
    assert [x for x in caplog.records if x.levelno >= logging.WARNING] == []
    assert f"tapesift UI: http://127.0.0.1:{port}/" in r.stderr
    assert be.opened == []  # CliRunner's stderr is not a TTY


# 23
def test_non_loopback_warns(
    be: Backends, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    hosts = _spy_allowed_hosts(monkeypatch)
    port = _free_port()
    with caplog.at_level(logging.WARNING):
        r = runner.invoke(
            app,
            ["serve", "--out", str(_index(tmp_path)), "--host", ANY_HOST, "--port", str(port)],
        )
    assert r.exit_code == ExitCode.OK, r.stderr
    warnings = [x for x in caplog.records if x.levelno == logging.WARNING]
    assert [x.getMessage() for x in warnings] == [
        f"serving on {ANY_HOST}:{port} with no authentication: anyone who can reach this address "
        "can search the index and play every indexed file"
    ]
    assert hosts == [["*"]]
    assert be.opened == []


# 24
def test_cli_import_stays_light() -> None:
    code = (
        "import sys, tapesift.cli; "
        "print(sorted({'fastapi','starlette','uvicorn','lancedb','onnxruntime','torch'} "
        "& set(sys.modules)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert out.stdout.strip() == "[]"
