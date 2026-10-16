# 0004. Name the project tapesift, license it Apache-2.0, build in public from day one

Date: 2026-10-16   Status: accepted (plan defaults D1, D3, D11)   Tier: T3

## Context
The package name, the license and repo visibility are the three hardest things to change after launch. `tapesift` was free on PyPI on Oct 13, 2026 (`reelsift` and `framesift` also free).

## Options
Name: `tapesift`, `reelsift`, `framesift`. License: Apache-2.0, MIT, AGPL-3.0. Visibility: public now, public at launch.

## Decision
- Name `tapesift`: "tape" covers audio and video and sounds like archives, which is who pays.
- Apache-2.0: patent grant, business-friendly, standard for open-core infrastructure. MIT lacks the patent grant; AGPL would scare off the enterprise users the business needs.
- Public from day one: build in public needs visible commits.

## Consequences
Anyone can fork and host it; the moat is the cost numbers, domain packs and speed of iteration, not the license. The name must be registered on PyPI (TestPyPI first) before someone else takes it.

## Revisit if
The PyPI name is taken before E8, or a trademark conflict appears.
