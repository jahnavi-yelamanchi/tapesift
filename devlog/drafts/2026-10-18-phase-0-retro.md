# Phase 0 retro (draft, 2026-10-18)

Scope: Phase 0 setup (P0.1 to P0.7), then the first engine milestone that ran alongside it (M0, E1, E2, #12). Period: 2026-10-16 to 2026-10-18.

PRs merged in the period: #2, #3, #7, #8, #10, #17, #18, #19, #20, #22, #23. #1 was closed unmerged on purpose (P0.4 gate check, a lint-blocks-merge experiment).

## What worked

- Parallel worktree builders on E1 (#18) and E2 (#19). Each builder worked in its own worktree.
- Reviewer and test-auditor caught real bugs:
  - FFmpeg `concat:` protocol injection. A name like `concat:a|b` could reach other files. Fixed with a `file:` whitelist (`src/tapesift/media/probe.py`, `decode.py`). Tests for it were added in 819a972 on the #18 branch.
  - Weak tests. The #22 tests checked only shapes and monotonic times. The fix pins values from the spec tables.
- Owner cards settled the mismatches between the specs and PyAV 19. The E1 HDR card was answered: probe opens the codec context and decodes no frames.
- Fresh-clone check: `uv sync && make check` from a clean clone passed on 2026-10-18.

## What didn't

- Opus fan-out hit HTTP 429. Coding and review subagents moved to sonnet (#20). Opus stays for decisions.
- Parallel planners wrote the dependent specs before the interface spec. They diverged. Rule added (#7): the interface spec is written, critiqued and approved first, then the dependent specs are planned against it.
- A builder's test passed on the old code. The test did not catch the bug it was meant to catch.
- A read-only test-auditor left the main checkout on a detached HEAD. Read-only agents must work only in their own scratch clone.
- The scribe could not edit `docs/status.md` at session start. Its scope was stale.
- CHANGELOG conflicts between parallel PRs. Each PR adds lines under Unreleased, so the merges conflict.

## Open items from Phase 0

- Rotation-direction mutation not run (blocked by a permission check). Covered by reasoning through the rot90 pixel test only.

## Proposed changes (for the owner to approve)

Nothing here is applied. CLAUDE.md, AGENTS.md and `.claude/` are not edited.

(i) Auditor and reviewer prompts: never check out a branch in the main tree. Work only in a scratch clone.

(ii) Mutation runs become a standard test-auditor step. Inject bugs, record which were caught and which survived, and add a test for each survivor.

(iii) CHANGELOG conflicts. Options: towncrier-style fragments (one file per PR, assembled at release), or accept manual merges. Owner picks one.

(iv) The lead checks each reviewer suggestion against the spec before forwarding it. This is already practice (the #22 `start_offset` case, where a suggested value of about 0 was wrong and the spec says about 1.52 s). Write it into `docs/workflow.md` so it is explicit.

## Approval

- [ ] (i)
- [ ] (ii)
- [ ] (iii), choice:
- [ ] (iv)
