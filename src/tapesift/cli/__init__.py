"""Command-line entry point.

Exit codes mean the same thing for every command:
0 all good, 1 finished but some files failed, 2 bad config or arguments,
3 environment problem (missing GPU, missing model).
"""

import json
from enum import IntEnum
from pathlib import Path
from typing import Annotated

import typer

from tapesift import __version__
from tapesift.cli.doctor import Probes, diagnose, render


class ExitCode(IntEnum):
    OK = 0
    PARTIAL_FAILURE = 1
    BAD_INPUT = 2
    ENVIRONMENT = 3


app = typer.Typer(
    name="tapesift",
    help="Turn hours of video and audio into searchable, timestamped data.",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"tapesift {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
) -> None:
    """Turn hours of video and audio into searchable, timestamped data."""


JsonOption = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


@app.command()
def doctor(as_json: JsonOption = False) -> None:
    """Report Python, FFmpeg, CUDA, GPUs, NVDEC and free disk, and pick a hardware profile."""
    report = diagnose(Probes(), Path.cwd(), __version__)
    if as_json:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        typer.echo(render(report))
    raise typer.Exit(ExitCode.ENVIRONMENT if report.problems else ExitCode.OK)


from tapesift.cli.search import search  # noqa: E402  (needs ExitCode, app and JsonOption above)

app.command()(search)

from tapesift.cli.serve import serve  # noqa: E402  (needs ExitCode and app above)

app.command()(serve)

from tapesift.cli.index import index  # noqa: E402  (needs ExitCode, app and JsonOption above)

app.command()(index)


def main() -> None:
    app()
