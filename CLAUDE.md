@AGENTS.md

## Claude Code only
- Claude Code subagents only; no Codex (ADR 0009).
- Every step fans out to several subagents, every time. Never do a step's work inline in the lead session:
  - spec: `planner` per issue, then `spec-critic` per draft, in parallel;
  - build: one `feature-builder` per approved spec, in parallel, each in its own worktree;
  - review: `reviewer` and `test-auditor` in parallel on every PR, then verify their findings;
  - fix: resume the same builder with SendMessage;
  - T3: two `council` subagents (opus and sonnet), then a rebuttal round;
  - bookkeeping: `scribe`.
- planner writes specs; test-writer writes tests; fixture-maker makes fixtures.
- Helpers you call during a feature work inside your worktree; never give them their own.
- Use the ship-feature skill before opening any PR.
- Commits: Conventional Commits, no Co-Authored-By trailer for Claude (owner's rule).
