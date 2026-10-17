# 0011. Raise the Python floor to 3.12

Date: 2026-10-16   Status: accepted (supersedes 0005)   Tier: T2

## Context
The floor is raised ahead of M0 (#4), which adds `av>=19.0.1` and `numpy>=2.5.4`. Both require Python >=3.12 (sources: https://pypi.org/project/av/, https://pypi.org/project/numpy/). Keeping 3.11 means pinning older decoder and array versions for 3.11 users only.

## Options
1. Keep 3.11 with a split lock (older `av` and numpy on 3.11, current on 3.12+). Pros: no user dropped. Cons: two decoder versions to test and debug, timestamp behavior can differ between them.
2. Raise the floor to 3.12. Pros: one decoder version under test, one lock resolution. Cons: drops users installing into an existing 3.11 environment.

## Decision
Raise the floor: `requires-python = ">=3.12"`. CI tests ubuntu 3.12 (the floor), ubuntu 3.13 and macOS 3.12. Ruff targets `py312`, pyright checks against 3.12.

## Consequences
`uvx` fetches a 3.12 interpreter for users who lack one, so most installs are unaffected. Only one PyAV and numpy version is under test. 3.12 syntax (`type X = ...`, PEP 695 generics) is now allowed.

## Revisit if
A target platform pins 3.11.
