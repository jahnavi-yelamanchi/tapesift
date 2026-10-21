# 0014. Lean mode until the MVP demo works; web UI and robotics search move into v0.1

Date: 2026-10-20   Status: proposed (draft in docs/adr/drafts/; move to docs/adr/ and mark accepted when merged)   Tier: T2   Amends: ADR 0009 (agent fan-out), ADR 0013 (v0.1 scope)

## Context
The full process in ADR 0009 and the 2026-10-17 amendment fans out every step: a planner and a spec-critic per spec, a council for each one-way door, a reviewer and a test-auditor per PR, and a scribe. A feature cost 5 to 8 agents and the suite reached 600+ tests. The account's usage ran out while the product still could not index and search a video. The owner's judgement: the overhead is out of proportion to what is shipping.

Scope also changed. Users include robotics teams, and the first target example is search over the Open X-Embodiment dataset. Terminal-only is not enough for v0.1, so `tapesift serve` moves up from v0.3 into v0.1.

## Options
1. Keep the full process. Pros: two reviewers and a council on every one-way door. Cons: the usage cost above, with no working demo.
2. Lean mode until the MVP demo works. One `feature-builder` per approved spec, one `reviewer` pass per PR, models as below. Pros: a demo sooner; less usage per feature. Cons: fewer lenses on each PR; same model family on build and review.
3. Lean mode with the council kept for T3 only. Pros: keeps one debate for the costliest calls. Cons: the owner has now said no council by default; a T3 still gets a decision card from the lead.

## Decision
Option 2, with the web UI and robotics search added to v0.1 (owner, 2026-10-20).

1. **Lean mode until the MVP demo works.**
   - One `feature-builder` per approved spec, each in its own worktree. One `reviewer` pass per PR.
   - No `spec-critic`, no `council`, no `test-auditor` by default. The owner can call any of them on a specific PR.
   - Test sets are smaller: acceptance tests plus dangerous cases, about 15 to 35 per spec.
   - The opus planner and the opus lead write decision cards themselves. Only these go to the owner: spend above about $5, credentials, and security.
2. **Models.** Opus only for decisions (`planner`, the lead session). Sonnet for every other subagent (`feature-builder`, `test-writer`, `fixture-maker`, `reviewer`, and `spec-critic` if called). Haiku for `scribe`. Pass `model` explicitly when dispatching.
3. **Web UI in v0.1.** `tapesift serve` moves from v0.3 to v0.1. Spec: [docs/specs/40-web-ui.md](../../specs/40-web-ui.md) (being written; not yet merged).
4. **Robotics episodes in v0.1.** Spec: [docs/specs/41-robotics-episodes.md](../../specs/41-robotics-episodes.md) (being written; not yet merged). First target: search over Open X-Embodiment.
   - Open question for the owner: licences differ by sub-dataset. Each sub-dataset's licence must be checked before ingest. That is a licensing call (AGENTS.md), so it gets its own decision card.
   - Any cloud run is on Modal (ADR 0008). A run above about $5 goes to the owner first.
5. **Reversion.** After the MVP demo, the full process returns. The owner makes that call.

## Consequences
- v0.1 has more scope and less process. The v0.1 window (Oct 19 to Nov 1) gets tighter. The feature freeze in ADR 0013 (Oct 28) may need to move; the owner decides.
- Fewer tokens per feature. Review is one lens and one model family, so CI, the fixture smoke suite and the owner's own review carry more weight (the same risk ADR 0009 named).
- Smaller test sets mean dangerous-case coverage is the thing to protect. The spec's dangerous cases are not optional.
- `docs/workflow.md` and the full-process text in `CLAUDE.md` describe the heavy process until they are edited.

## Proposed edit to CLAUDE.md (not applied yet)
The "Claude Code only" block in `CLAUDE.md` is to be replaced with the text below. It is written here because this run may only write under `docs/adr/drafts/`, `devlog/drafts/`, and a few docs files. The owner or the lead applies it.

```
## Claude Code only (lean mode, ADR 0014; reverts to the full process after the MVP demo, by owner call)
- Start every session by reading docs/status.md and `gh issue list --label follow-up`.
- Claude Code subagents only; no Codex (ADR 0009).
- Lean: one feature-builder per approved spec (own worktree), one reviewer pass per PR. No spec-critic, council or test-auditor by default.
- Models: opus only for decisions (planner, the lead session); sonnet for all other coding, test and review subagents; haiku for scribe. Pass `model` explicitly.
- Lead makes T2/T3 decision cards itself. Owner gets only: spend above about $5, credentials, security.
- Tests per spec: acceptance plus dangerous cases (about 15 to 35).
- Use the ship-feature skill before opening any PR. Draft PRs only.
- Commits: Conventional Commits, no Co-Authored-By trailer for Claude (owner's rule).
```

## Revisit if
- The MVP demo works: the full process returns (owner's call).
- A bug that the lean review missed reaches main twice. Then add the test-auditor back on PRs that touch media, store or runner.
- v0.1 misses the Nov 1 window with the UI and robotics in scope. Then the owner cuts scope; the UI or robotics comes out, not the test floor.
