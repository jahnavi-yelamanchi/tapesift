"""Fail a PR that quietly weakens the test suite.

Two rules from docs/workflow.md ("Machine checks that make trust cheaper"):
1. No test file may lose test functions compared to the base branch.
2. An added skip or xfail must cite a decision card or ADR on the same line,
   e.g. `@pytest.mark.skip(reason="card #41: NVDEC missing on runners")`.

Usage: python scripts/ci/test_guard.py --base origin/main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+test_\w*\s*\(", re.MULTILINE)
# Decorators at the start of a line, or skip/xfail/importorskip calls.
SKIP = re.compile(
    r"^\s*@pytest\.mark\.(?:skip|skipif|xfail)\b|\bpytest\.(?:skip|xfail|importorskip)\("
)
CITATION = re.compile(r"(?:card\s*#\d+|ADR[\s-]*\d{4})", re.IGNORECASE)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, timeout=60
    ).stdout


def count_tests(source: str) -> int:
    # ponytail: counts `def test_` statically; parametrize cases are not counted.
    # Switch to `pytest --collect-only` per side if someone games this with parametrize.
    return len(TEST_DEF.findall(source))


def lost_tests(base: str) -> list[str]:
    problems: list[str] = []
    for path in git("diff", "--name-only", f"{base}...HEAD", "--", "tests").split():
        if not path.endswith(".py"):
            continue
        try:
            before = count_tests(git("show", f"{base}:{path}"))
        except subprocess.CalledProcessError:
            continue  # new file
        try:
            after = count_tests(git("show", f"HEAD:{path}"))
        except subprocess.CalledProcessError:
            after = 0  # deleted file
        if after < before:
            problems.append(f"{path}: {before} -> {after} test functions")
    return problems


def uncited_skips(diff: str) -> list[str]:
    problems: list[str] = []
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and SKIP.search(line[1:]) and not CITATION.search(line):
            problems.append(f"{current}: {line[1:].strip()}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    base = parser.parse_args().base

    problems = lost_tests(base)
    problems += uncited_skips(git("diff", "-U0", f"{base}...HEAD", "--", "*.py"))
    for problem in problems:
        print(f"test-guard: {problem}", file=sys.stderr)
    if problems:
        print(
            "test-guard: tests were removed or skipped without a decision card. "
            "Cite `card #N` or `ADR NNNN` on the same line, or restore the tests.",
            file=sys.stderr,
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
