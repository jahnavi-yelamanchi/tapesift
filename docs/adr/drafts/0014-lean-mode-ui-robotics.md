# 0014. Lean mode until the MVP demo works; web UI moves into v0.1

Date: 2026-10-20   Status: proposed (draft in docs/adr/drafts/; move to docs/adr/ and mark accepted when merged)   Tier: T2   Amends: ADR 0009 (agent fan-out), ADR 0013 (v0.1 scope)

## Context
The full process in ADR 0009 and the 2026-10-17 amendment fans out every step: a planner and a spec-critic per spec, a council for each one-way door, a reviewer and a test-auditor per PR, and a scribe. A feature cost 5 to 8 agents and the suite reached 600+ tests. The account's usage ran out while the product still could not index and search a video. The owner's judgement: the overhead is out of proportion to what is shipping.

Scope also changed. Terminal-only is not enough for v0.1, so `tapesift serve` (a web UI) moves up from v0.3 into v0.1. The MVP is general video only. Robotics datasets (for example Open X-Embodiment) were an example of possible users, not a v0.1 target; they are a later use case.

## Options
1. Keep the full process. Pros: two reviewers and a council on every one-way door. Cons: the usage cost above, with no working demo.
2. Lean mode until the MVP demo works. One `feature-builder` per approved spec, one `reviewer` pass per PR, models as below. Pros: a demo sooner; less usage per feature. Cons: fewer lenses on each PR; same model family on build and review.
3. Lean mode with the council kept for T3 only. Pros: keeps one debate for the costliest calls. Cons: the owner has now said no council by default; a T3 still gets a decision card from the lead.

## Decision
Option 2, with the web UI added to v0.1 (owner, 2026-10-20).

1. **Lean mode until the MVP demo works.**
   - One `feature-builder` per approved spec, each in its own worktree. One `reviewer` pass per PR.
   - No `spec-critic`, no `council`, no `test-auditor` by default. The owner can call any of them on a specific PR.
   - Test sets are smaller: acceptance tests plus dangerous cases, about 15 to 35 per spec.
   - The opus planner and the opus lead write decision cards themselves. Only these go to the owner: spend above about $5, credentials, and security.
2. **Models.** Opus only for decisions (`planner`, the lead session). Sonnet for every other subagent (`feature-builder`, `test-writer`, `fixture-maker`, `reviewer`, and `spec-critic` if called). Haiku for `scribe`. Pass `model` explicitly when dispatching.
3. **Web UI in v0.1.** `tapesift serve` moves from v0.3 to v0.1. Spec: [docs/specs/40-web-ui.md](../../specs/40-web-ui.md) (being written; not yet merged).
4. **v0.1 is general video only.** Robotics datasets (for example Open X-Embodiment) are a "Later" use case. No robotics spec in v0.1.
5. **Reversion.** After the MVP demo, the full process returns. The owner makes that call.

## Consequences
- v0.1 has a web UI and less process. The v0.1 window (Oct 19 to Nov 1) gets tighter. The feature freeze (ADR 0013, Oct 28) stays unless the owner moves it.
- Fewer tokens per feature. Review is one lens and one model family, so CI, the fixture smoke suite and the owner's own review carry more weight (the same risk ADR 0009 named).
- Smaller test sets mean dangerous-case coverage is the thing to protect. The spec's dangerous cases are not optional.
- `docs/workflow.md` still describes the heavy process until it is edited.

## CLAUDE.md
The lean-mode "Claude Code only" block is applied to `CLAUDE.md` by the owner's commit `74031b4` on `docs/lean-mode`. This ADR does not restate it.

## Revisit if
- The MVP demo works: the full process returns (owner's call).
- A bug that the lean review missed reaches main twice. Then add the test-auditor back on PRs that touch media, store or runner.
- v0.1 misses the Nov 1 window with the web UI in scope. Then the owner cuts scope; the UI comes out only if the owner decides so, not the test floor.
