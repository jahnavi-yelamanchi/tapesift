# Agent metrics

Updated by the scribe from git and PR history; read on Sundays. Definitions in docs/workflow.md, Learning loop.

| Week | PRs merged | Merged without edits | Review rounds / PR | Bugs caught (reviewer / test-auditor / CI / owner) | Cards (override rate) | Issue-to-merge | Post-merge bugs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-18 | 11 | not measured | not measured | not measured | not scored (picks blank, #16) | not measured | none known |
| 2026-10-18 (partial, #34 merged 2026-10-20) | 1 (#34) | not measured | not logged | test-auditor: 16 of 19 injected bugs caught (3 equivalent); reviewer not logged | not scored (picks blank, #16); 10 M1 cards decided, 7 by council | not measured | none known |
| 2026-10-20 to 10-29 (lean phase, #37 to #51) | 13 (#37, #38, #40, #41, #42, #44, #45, #46, #47, #48, #49, #50, #51) | not measured | not logged | not logged; known post-merge bug: #50 (Whisper output on a steady tone, shipped in #46) | not scored (picks blank, #16) | not measured | 1 known (#50) |

Other numbers (2026-10-29): 1016 tests collected on main; speech WER 0.067 on `speech.mp4` (bound 0.20); captions 1.81 s per frame on 4 vCPU; Modal spend in the lean phase about $0.07 (E4 bench).
