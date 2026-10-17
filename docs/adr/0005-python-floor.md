# 0005. Support Python 3.11 and newer; develop on 3.12

Date: 2026-10-16   Status: superseded by 0011   Tier: T2

## Context
Users install with `uvx`, which fetches a Python if needed, so the floor mostly affects people installing into an existing environment. ML wheels (PyAV, faster-whisper, torch, lancedb) lag the newest Python by months.

## Options
1. 3.11 floor. Pros: wide install base, `Self`, `tomllib`, exception groups. Cons: no PEP 695 generics syntax.
2. 3.12 floor. Pros: newer typing syntax. Cons: drops users on 3.11 (still the default on many servers).
3. 3.10 floor. Cons: no `tomllib`, weaker typing.

## Decision
`requires-python = ">=3.11"`. Local development and the Linux CI job pin 3.12 via `.python-version`; CI also runs the floor (3.11) so we never use newer syntax by accident.

## Consequences
Code avoids 3.12-only syntax (`type X = ...`, PEP 695 generics).

## Revisit if
A required dependency drops 3.11.
