"""`tapesift index` (docs/specs/30-runner.md). Module-level imports stay light (R6): the runner,
the pipeline, rich and the store load inside the command."""

from __future__ import annotations

import json
import math
import signal
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated

import typer

from tapesift.cli import ExitCode, JsonOption
from tapesift.config import ConfigError, ModelLoadError, Profile, load_config


def _fail(message: str, code: int) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code)


def index(
    paths: Annotated[list[Path], typer.Argument(exists=True, help="Files or folders to index.")],
    config: Annotated[
        Path | None, typer.Option("--config", help="Config file (default ./tapesift.toml).")
    ] = None,
    profile: Annotated[
        Profile | None,
        typer.Option("--profile", help="cpu, gpu or server (default: doctor picks)."),
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="Index folder, relative to the current directory.")
    ] = None,
    max_media_hours: Annotated[
        float | None,
        typer.Option("--max-media-hours", help="Stop starting new files after H hours of media."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Probe and print the plan; write nothing.")
    ] = False,
    full_hash: Annotated[
        bool, typer.Option("--full-hash", help="sha256 of whole files as asset IDs (slower).")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Index files and folders: transcripts and captions, searchable with `tapesift search`."""
    from tapesift.runner import run as rr

    restore = rr.install_interrupt_handlers()
    try:
        _index(paths, config, profile, out, max_media_hours, dry_run, full_hash, as_json)
    except KeyboardInterrupt as e:
        typer.echo("interrupted", err=True)
        raise typer.Exit(
            128 + (e.signum if isinstance(e, rr.Interrupted) else signal.SIGINT)
        ) from None
    finally:
        restore()


def _index(
    paths: list[Path],
    config: Path | None,
    profile: Profile | None,
    out: Path | None,
    max_media_hours: float | None,
    dry_run: bool,
    full_hash: bool,
    as_json: bool,
) -> None:
    import logging

    from rich.console import Console
    from rich.logging import RichHandler
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

    from tapesift.pipeline import index as pi
    from tapesift.runner import run as rr
    from tapesift.runner.report import render, to_dict

    if max_media_hours is not None and not (math.isfinite(max_media_hours) and max_media_hours > 0):
        raise typer.BadParameter(
            "must be a positive number of hours of media", param_hint="--max-media-hours"
        )
    try:
        cfg = load_config(config, profile=profile, out_dir=out)
    except ConfigError as e:
        raise _fail(str(e), ExitCode.BAD_INPUT) from None
    try:
        cfg = pi.resolve_config(cfg)
    except ModelLoadError as e:
        raise _fail(str(e), ExitCode.ENVIRONMENT) from None

    err = Console(stderr=True)
    log = logging.getLogger("tapesift")
    if not log.handlers:
        log.addHandler(RichHandler(console=err, show_path=False, markup=False))
        log.setLevel(logging.INFO)

    bar = err.is_terminal and not as_json
    lance = None
    if not dry_run:
        from tapesift.store import lance  # loads lancedb (R6: not for a dry run)

    bar_ctx = (
        Progress(
            TextColumn("{task.description}", markup=False),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=err,
            transient=False,
            redirect_stdout=False,  # a swallowed stdout or stderr would lose results and errors
            redirect_stderr=False,
        )
        if bar
        else nullcontext()
    )
    aborted: rr.RunAborted | None = None
    # The try wraps the bar, so an error prints after the bar has stopped.
    try:
        with bar_ctx as prog:
            task = prog.add_task("", total=None) if prog is not None else None

            def progress(done: int, total: int, current: str) -> None:
                if prog is not None and task is not None:
                    prog.update(task, total=total, completed=done, description=current)

            summary = rr.run_index(
                paths,
                cfg,
                load=pi.load,
                open_store=None if dry_run else pi.open_store,
                full_hash=full_hash,
                max_media_hours=max_media_hours,
                progress=progress,
            )
    except rr.OutDirError as e:
        raise _fail(str(e), ExitCode.BAD_INPUT) from None
    except rr.RunAborted as e:
        aborted, summary = e, e.summary  # print what finished, then exit 3
    except ModelLoadError as e:
        raise _fail(str(e), ExitCode.ENVIRONMENT) from None
    except OSError as e:
        raise _fail(f"cannot use {cfg.out_dir}: {e.strerror or e}", ExitCode.BAD_INPUT) from None
    except Exception as e:
        if lance is not None and isinstance(e, lance.StoreError):
            raise _fail(str(e), ExitCode.BAD_INPUT) from None
        raise

    if summary.interrupted_by is not None:
        rr.exit_on_next_signal(summary.interrupted_by)
    if as_json:
        typer.echo(json.dumps(to_dict(summary), ensure_ascii=False, indent=2))
    else:
        typer.echo(render(summary), err=True)
    if aborted is not None:
        raise _fail(str(aborted), ExitCode.ENVIRONMENT)
    if summary.interrupted_by is not None:
        raise typer.Exit(128 + summary.interrupted_by)
    raise typer.Exit(ExitCode(summary.exit_code))
