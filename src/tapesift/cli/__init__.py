"""Command-line entry point.

Exit codes mean the same thing for every command:
0 all good, 1 finished but some files failed, 2 bad config or arguments,
3 environment problem (missing GPU, missing model).
"""

from enum import IntEnum
from typing import Annotated

import typer

from tapesift import __version__


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


def main() -> None:
    app()
