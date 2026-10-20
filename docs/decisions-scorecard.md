# Decisions scorecard

One row per decision card. Write your pick before reading the agent's. Fill "Who was right" when the outcome is known.

| Date | Card | Tier | My pick | Agent pick | Final | Who was right | Lesson |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-16 | Speech fixtures (ADR 0007) | T2 | | A | A, English only | | |
| 2026-10-16 | Language scope (ADR 0010) | T3 | English only | (not asked) | English only | | |
| 2026-10-17 | M0 T3 cards (7) | T3 | council version | planner: min-of-streams duration, PARTIAL_DECODE for unopenable | council version | council (pending evidence) | |
| 2026-10-17 | Asset ID (ADR 0012) | T3 | | planner: sha256: prefix | tsid1:/sha256: | | |
| 2026-10-17 | Python floor (ADR 0011) | | | keep 3.11 (planners) | 3.12 (owner) | | |
| 2026-10-20 | M1 card 1: unexpected per-file exceptions (ADR 0013, M1-1) | T3 | | opus: C; sonnet: C (both = rec) | C, failure marker, 2 attempts per version | | |
| 2026-10-20 | M1 card 2: nullable `shot` and `conf` (ADR 0013, M1-2) | T3 | | opus: A; sonnet: A (both = rec) | A, `shot: null` in v0.1 | | |
| 2026-10-20 | M1 card 3: `search --json` shape (ADR 0013, M1-3) | T3 | | opus: A; sonnet: A (both = rec) | A, `{query, hits}` with `trust` | | |
| 2026-10-20 | M1 card 4: config keys, defaults, `--config` (ADR 0013, M1-4) | T3 | | after rebuttal: opus A + config-folder paths; sonnet A + `max_batch` auto per profile | A, with `max_batch` None resolved per profile and config-folder paths | | |
| 2026-10-20 | M1 card 5: `"eng"` vs `"en"` (ADR 0013, M1-5) | T3 | | opus: A; sonnet: A (both = rec) | A, two documented meanings | | |
| 2026-10-20 | M1 card 6: backend ids in provenance (ADR 0013, M1-6) | T3 | | opus: A; sonnet: A (both = rec) | A, `<backend>:<model>@<rev>` | | |
| 2026-10-20 | M1 card 7: LGPL `num2words` (ADR 0013, M1-7) | T3, licensing | | first round: opus shim, sonnet A (vision extra and THIRD_PARTY); after rebuttal sonnet moved to shim | guarded shim, no num2words, transformers pinned | | |
