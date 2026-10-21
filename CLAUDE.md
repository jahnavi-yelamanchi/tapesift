@AGENTS.md

## Claude Code only (lean mode, ADR 0014; reverts to the full process after the MVP demo, by owner call)
- Start every session by reading docs/status.md (where the build is, decisions, what waits on the owner) and `gh issue list --label follow-up`.
- Claude Code subagents only; no Codex (ADR 0009).
- Lean (owner, 2026-10-20): one `feature-builder` per approved spec, each in its own worktree; one `reviewer` pass per PR, then verify its findings; fix by resuming the same builder with SendMessage. No spec-critic, council or test-auditor by default.
- Models: opus only for decisions (`planner`, the lead); sonnet for all other coding, test and review subagents; haiku for `scribe`. Pass `model` explicitly.
- The lead (opus) decides T2/T3 cards itself. The owner gets only: spend above about $5, credentials, security.
- Tests per spec: acceptance plus dangerous cases (about 15 to 35).
- planner writes specs; test-writer writes tests; fixture-maker makes fixtures.
- Helpers you call during a feature work inside your worktree; never give them their own.
- Use the ship-feature skill before opening any PR. Draft PRs only.
- Commits: Conventional Commits, no Co-Authored-By trailer for Claude (owner's rule).
