"""Every `tapesift <cmd> --flag` in the README's code blocks exists in the typer app."""

import re
import shlex
from pathlib import Path

import pytest
import typer.main

from tapesift.cli import app

README = Path(__file__).resolve().parents[2] / "README.md"
BLOCK = re.compile(r"```(?:bash|sh|console)?\n(.*?)```", re.DOTALL)


def readme_invocations(text: str) -> list[list[str]]:
    """Argument lists (after `tapesift`) for every `tapesift ...` line in a fenced block."""
    found: list[list[str]] = []
    for block in BLOCK.findall(text):
        for line in block.splitlines():
            for part in line.split("&&"):
                words = shlex.split(part, comments=True)
                if "tapesift" in words:
                    found.append(words[words.index("tapesift") + 1 :])
    return found


def check(args: list[str]) -> str | None:
    """None if the command and every --flag exist, else a reason."""
    cmd = typer.main.get_command(app)
    for word in args:
        if word.startswith("--"):
            known = {o for p in cmd.params for o in (*p.opts, *p.secondary_opts)}
            if word.split("=")[0] not in known | {"--help"}:
                return f"unknown flag {word}"
        elif word in getattr(cmd, "commands", {}):
            cmd = getattr(cmd, "commands")[word]  # noqa: B009  (typer's Command type has no .commands)
        elif hasattr(cmd, "commands"):
            return f"unknown command {word}"
    return None


def test_readme_has_quickstart_commands() -> None:
    seen = {a[0] for a in readme_invocations(README.read_text()) if a}
    assert {"doctor", "index", "search", "serve"} <= seen


def test_every_readme_command_and_flag_exists() -> None:
    problems = [
        f"tapesift {' '.join(a)}: {why}"
        for a in readme_invocations(README.read_text())
        if (why := check(a))
    ]
    assert not problems


@pytest.mark.parametrize(
    "text",
    [
        "```bash\ntapesift index ./x --ouut out/\n```",
        "```bash\nuv run tapesift serch q\n```",
    ],
)
def test_misspellings_are_caught(text: str) -> None:
    assert any(check(a) for a in readme_invocations(text))
