import subprocess
import sys

from typer.testing import CliRunner

from tapesift import __version__
from tapesift.cli import ExitCode, app

runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == ExitCode.OK
    assert result.stdout.strip() == f"tapesift {__version__}"


def test_no_arguments_is_a_usage_error() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == ExitCode.BAD_INPUT


def test_python_dash_m_entry_point() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "tapesift", "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert out.stdout.strip() == f"tapesift {__version__}"
