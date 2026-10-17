@AGENTS.md

## Claude Code only
- Start every session by reading docs/status.md (where the build is, decisions, what waits on the owner) and `gh issue list --label follow-up`.
- Claude Code subagents only; no Codex (ADR 0009).
- Lead session only (subagents ignore this block and follow their own file): every step fans out to several subagents, every time. Never do a step's work inline in the lead session:
  - spec: `planner` per issue, then `spec-critic` per draft, in parallel. Exception: when specs share a
    new interface, the interface spec is written, critiqued and approved first, then the dependent
    specs are planned against it (retro, 2026-10-16);
  - build: commit approved specs on local main, then one `feature-builder` per spec, in parallel, each in its own worktree;
  - review: `reviewer` and `test-auditor` in parallel on every PR, then verify their findings;
  - fix: resume the same builder with SendMessage;
  - T3: two `council` subagents, Agent `model` set to opus and sonnet, then a rebuttal round;
  - bookkeeping: `scribe`.
- planner writes specs; test-writer writes tests; fixture-maker makes fixtures.
- Helpers you call during a feature work inside your worktree; never give them their own.
- Use the ship-feature skill before opening any PR.
- Commits: Conventional Commits, no Co-Authored-By trailer for Claude (owner's rule).
