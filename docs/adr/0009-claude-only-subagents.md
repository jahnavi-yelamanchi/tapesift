# 0009. Build with Claude Code subagents only, several per step; drop Codex

Date: 2026-10-16   Status: accepted (owner's call)   Tier: T2   Supersedes: plan decision D15, the Claude/Codex lane split

## Context
The plan split lanes between Claude Code (Core, Train, Docs) and Codex (Media, Eval), with each tool reviewing the other's PRs, run side by side in herdr panes. The owner would rather run many Claude subagents than switch between two tools, and asked for multiple subagents at every step, every time.

Facts that shape the design (code.claude.com/docs/en/sub-agents and /worktrees, checked 2026-10-16):
- Subagents can spawn subagents up to three layers below the main session.
- `isolation: worktree` gives a subagent its own checkout; it branches from `worktree.baseRef` (`fresh` = remote default branch, `head` = local HEAD).
- A finished subagent can be resumed with SendMessage and keeps its full context, so the builder that wrote a PR also fixes its review findings.
- 20 concurrent subagents by default.
- `Agent(type, ...)` allowlists are ignored inside subagent definitions, so which helpers a builder may call is enforced by its prompt.

## Options
A. Keep Claude + Codex. Pros: two vendors miss different bugs. Cons: two tools, two configs, the switching the owner wants to avoid.
B. Claude only, one subagent per step. Cons: one reviewer sharing the builder's blind spots.
C. Claude only, several subagents per step, with different lenses and different models on review. Pros: one tool; parallel by default; review diversity from lens and model rather than vendor. Cons: same model family; more tokens per feature.

## Decision
C. Every step fans out:

| Step | Subagents | Runs |
| --- | --- | --- |
| Spec | `planner` per issue, then `spec-critic` per spec | parallel across issues |
| Tests | `test-writer`, `fixture-maker` when a new media case is needed | inside the builder's worktree |
| Build | one `feature-builder` per approved spec, `isolation: worktree` | parallel, one per lane path set |
| Review | `reviewer` (bugs, contracts) and `test-auditor` (test strength, evidence), both sonnet since 2026-10-17 | parallel per PR |
| Fix | the same `feature-builder`, resumed with SendMessage | one per PR |
| T3 decisions | two `council` subagents, one opus and one sonnet, then a rebuttal round | parallel, isolated |
| Bookkeeping | `scribe` (haiku) | nightly |

The lead Claude session dispatches all of it; herdr becomes optional (keeping sessions alive, the GPU pane).

## Consequences
- Lanes stay, because they stop parallel builders from touching the same paths; all lanes are Claude.
- "Bugs caught by Claude review vs Codex review" in docs/metrics.md becomes "by reviewer vs test-auditor vs CI vs owner".
- Same-family blind spots are a real risk. CI, the test-guard check, the fixture smoke suite and the owner's gate 3 carry more weight.
- More tokens per feature: scribe and test-auditor run on smaller models; one feature per builder session.

## Amendment 2026-10-17
Owner: sonnet for all coding, testing and review subagents (feature-builder, test-writer, fixture-maker, reviewer, test-auditor, spec-critic); opus only where decisions are made (planner, one council seat, the lead session). Reason: an Opus-heavy fan-out hit the account rate limit mid-review; Sonnet is enough for basic coding.

## Revisit if
After about 20 merged PRs, bugs found after merge are not near zero, or the owner keeps catching bugs both reviewers missed. Then add a second-vendor reviewer on review only.
