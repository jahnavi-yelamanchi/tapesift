"""`tapesift serve`: build the store from the index in out_dir and serve the local UI (spec 40).
Module-level imports: stdlib, typer, tapesift.cli and tapesift.config only. fastapi, uvicorn,
lancedb and the embedder are imported inside the command (R6), so `tapesift --help` works
without the serve extra."""

import contextlib
import importlib
import importlib.util
import ipaddress
import logging
import socket
import sys
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final

import typer

from tapesift.cli import ExitCode
from tapesift.config import ConfigError, ModelLoadError, load_config

if TYPE_CHECKING:
    from fastapi import FastAPI

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8765

log = logging.getLogger(__name__)


def serve_available() -> bool:
    """True when fastapi and uvicorn are importable (importlib.util.find_spec)."""
    return all(importlib.util.find_spec(m) is not None for m in ("fastapi", "uvicorn"))


def is_loopback(host: str) -> bool:
    """host == "localhost", or ipaddress.ip_address(host).is_loopback; a ValueError is False."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _run(app: "FastAPI", sock: socket.socket) -> None:
    """uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False,
    server_header=False, proxy_headers=False, timeout_keep_alive=5, lifespan="off")).run(
    sockets=[sock]). Tests patch this module attribute."""
    import uvicorn

    config = uvicorn.Config(
        app,
        log_level="warning",
        access_log=False,
        server_header=False,
        proxy_headers=False,
        timeout_keep_alive=5,
        lifespan="off",
    )
    uvicorn.Server(config).run(sockets=[sock])


def _fail(message: str, code: ExitCode) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code)


def serve(
    config: Annotated[
        Path | None, typer.Option("--config", help="Config file (default ./tapesift.toml).")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="Index folder, as given to tapesift index --out.")
    ] = None,
    host: Annotated[
        str,
        typer.Option("--host", help="Address to listen on. Default 127.0.0.1: this machine only."),
    ] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="Port to listen on.")] = (
        DEFAULT_PORT
    ),
) -> None:
    """Open a local web page to search the index and play each moment."""
    if not serve_available():
        raise _fail(
            'tapesift serve needs the serve extra: install "tapesift[serve]"', ExitCode.ENVIRONMENT
        )
    try:
        cfg = load_config(config, out_dir=out)
    except ConfigError as e:
        raise _fail(str(e), ExitCode.BAD_INPUT) from None
    if not (cfg.out_dir / "store").is_dir():
        raise _fail(
            f'no index at {cfg.out_dir}: run "tapesift index" first, or pass --out',
            ExitCode.BAD_INPUT,
        )

    # Dynamic imports keep the E6/E7 touchpoints in this one function (and R6: nothing heavy at
    # import time). ponytail: plain `from ... import` once E6 and E7 are on main.
    lance = importlib.import_module("tapesift.store.lance")
    embed = importlib.import_module("tapesift.vision.embed")
    try:
        store = lance.LanceStore(cfg, embed.OnnxEmbedder(cfg))
    except ModelLoadError as e:
        raise _fail(str(e), ExitCode.ENVIRONMENT) from None
    except lance.StoreError as e:
        raise _fail(str(e), ExitCode.BAD_INPUT) from None

    try:
        family = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][0]
        sock = socket.create_server((host, port), family=family)
    except OSError as e:
        raise _fail(
            f"cannot listen on {host}:{port}: {e.strerror or e}", ExitCode.BAD_INPUT
        ) from None

    try:  # the socket is closed on every path out, including a failure in create_app
        from tapesift.serve.app import LOOPBACK_HOSTS, create_app

        shown = f"[{host}]" if ":" in host else host  # the host as it appears in a Host header
        loopback = is_loopback(host)
        if loopback:
            allowed = sorted({*LOOPBACK_HOSTS, shown})
        else:
            allowed = ["*"]
            log.warning(
                "serving on %s:%s with no authentication: anyone who can reach this address "
                "can search the index and play every indexed file",
                host,
                port,
            )

        runner = importlib.import_module("tapesift.runner.run")
        assets_dir = cfg.out_dir / "assets"

        def scan() -> Mapping[str, str]:
            return runner.scan_assets(assets_dir)

        app = create_app(store, scan, allowed_hosts=allowed)
        # The literal bound address, so a name like localhost can't resolve to a family we
        # didn't bind.
        bound = str(sock.getsockname()[0])
        url = f"http://{f'[{bound}]' if ':' in bound else bound}:{port}/"
        typer.echo(f"tapesift UI: {url}  (Ctrl-C to stop)", err=True)
        if sys.stderr.isatty() and loopback:
            with contextlib.suppress(Exception):
                webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            _run(app, sock)
    finally:
        sock.close()
