# tapesift Agentic Workflow

Oct 13, 2026 · @jahnavi

## Operating model

You decide and review; Claude Code subagents build, and other Claude subagents check their work (ADR 0009: Claude only, several subagents per step). Every feature goes around the same loop, and you appear at four gates. This doc defines the roles, files, prompts and commands that make the loop run. The [build plan](https://claude.ai/code/artifact/2af96e92-7faf-4aa5-b828-ff39efedfac1) says what to build; this doc says how.

&#91;embedded content: build loop · 7 steps, 4 human gates\]

The loop closes through gate 4: each retro edits the files every agent reads at startup, so the next feature starts with the lesson already built in.

## Roles

One subagent builds; two others, on different models and with different lenses, review it in parallel. On hard decisions two council subagents advise separately and you decide. Model choices per role are a starting guess: track results (Learning loop section) and change them after about 10 PRs.

| Role | Played by | Owns | Never does |
| --- | --- | --- | --- |
| Tech lead | You | Specs you approve, decisions, merges, the four hand-written pieces, posts | Merges a PR without reading its tests and interface changes |
| Planner | Claude Code, `planner` subagent, Opus | Turns an issue into a spec, a task list and decision cards | Writes product code |
| Spec critic | Claude Code `spec-critic` subagent, sonnet, read-only | Attacks every draft spec before you see it | Edits anything |
| Feature builder | Claude Code `feature-builder` subagent, `isolation: worktree`, several in parallel | One complete feature: tests, code, docs, changelog line, PR | Adds dependencies, changes interfaces, or edits outside its scope without a decision card |
| Test writer | Claude Code `test-writer` subagent, called by a builder | Tests written from the spec, before or alongside code | Edits `src/` |
| Fixture maker | Claude Code `fixture-maker` subagent | Synthetic messy-data fixtures | Uses real or unlicensed footage |
| Reviewer | Claude `reviewer` subagent, opus, read-only | Bugs, wrong timestamps, crashes on bad files, spec drift, contract changes | Edits code |
| Test auditor | Claude `test-auditor` subagent, sonnet, read-only, in parallel with reviewer | Missing tests, tests that pass on broken code, claims without numbers | Edits code |
| Council | Two `council` subagents (opus and sonnet), asked separately | Options and a recommendation on one-way-door decisions | Decides |
| Scribe | Claude Code `scribe` subagent, small model | ADR drafts, changelog lines, devlog drafts, metrics | Posts, merges or pushes anything |

**Lanes** still exist, because they keep parallel builders off each other's paths: Core, Media, Eval, Train, Docs. Every lane is built by `feature-builder` subagents (ADR 0009).

## Human checkpoints and stop rules

You step in at four gates and nowhere else. Implementing, testing, fixing lint, opening PRs, reviewing and retrying CI all run without you.

| Gate | When | What you check | Time |
| --- | --- | --- | --- |
| 1. Approve spec | Before any code | Goal, acceptance commands, interfaces touched; the plan too if an interface, schema, CLI flag, config key or dependency changes | 5 to 10 min |
| 2. Decide | Whenever an agent raises a decision card | The options and the recommendation (Decision protocol section) | 2 to 15 min |
| 3. Merge | CI green, reviewer and test-auditor done | Tests first, then interface changes, then behavior on bad input | 10 to 30 min |
| 4. Approve context edits | After a retro proposes changes to `AGENTS.md`, a skill or a template | That the edit is small, general and wouldn't confuse other lanes | 5 min |

**An agent must stop and raise a decision card before it:**

- adds, removes or upgrades a dependency;
- changes a public interface, the output schema, a CLI command or flag, or a config key or default;
- deletes, skips, loosens or rewrites an existing test;
- edits files outside the paths in its spec;
- touches licensing, privacy, security, credentials or training data;
- starts anything that costs money (GPU rentals, paid APIs);
- fails the same error twice in a row (loop guard: it writes down what it tried and its best hypothesis, then stops);
- finds the spec ambiguous or self-contradictory.

How stopping looks in practice: the subagent ends its turn with the card as its last message, and the card surfaces in the lead session that dispatched it. A background session in `claude agents` shows as waiting. Nothing waits silently.

## Decision protocol

Every decision gets a tier. The tier decides who makes the call and what gets written down. Agents learn the tiers from `AGENTS.md`.

| Tier | Examples | Who decides | Record |
| --- | --- | --- | --- |
| T0, trivial | Local names, helper layout, test file structure | The agent | Nothing |
| T1, cheap to reverse | Internal module split, which approved library to use | The agent, by the rules of thumb in the plan | One line in the PR's Decisions list; you can veto at merge |
| T2, costly to reverse | New dependency, config key, default value, perf vs quality tradeoff | You, from a decision card | Card answer in the PR; scribe drafts an ADR if it will matter in a month |
| T3, one-way door | Output schema, CLI names, interfaces, license, training data, public benchmark claims | You, after the two-model council | ADR, including the losing option and the dissent |

**The decision card** (agents write exactly this, then stop):

```markdown
### Decision needed (T2 or T3): <one line>
Context: <2-3 lines, with numbers if any>
Options:
A. <option>. Pros: ... Cons: ...
B. <option>. Pros: ... Cons: ...
C. <option, if a real third exists>
Hardest to reverse: <A, B or C, and why>
Recommendation: <letter>, because <one reason>
Would change my mind: <evidence>
Blocked until answered: <what work waits>
```

**Your four possible answers:** pick a letter; pick a letter with a change ("B, but keep the old flag as an alias for one release"); "run this experiment first" (cheapest test, with a time cap); or "send to council".

**The two-model council, for T3.**

1. The lead dispatches two `council` subagents in parallel, one on opus and one on sonnet, with the same question (prompt P8). Neither sees the other's answer.
2. Paste each answer to the other and ask for a rebuttal (prompt P9).
3. You decide. If both agree and you disagree, write down why; that's either a lesson for you or a gap in their context.
4. The scribe drafts the ADR, including the option you rejected and the strongest argument for it.

**How this teaches you judgment:** before you read an agent's recommendation, write your own pick and one-line reason in the card. Then compare. Over a month, the cases where you and the agents disagreed, and who turned out right, are the most useful senior-engineering lessons in this project. The scribe logs them in `docs/decisions-scorecard.md`.

## Feature squads

A feature squad is one `feature-builder` subagent that takes one approved spec all the way to a ready PR in its own worktree, calling `test-writer` and `fixture-maker` as it goes. The lead dispatches squads in parallel: 2 at once in weeks 1 and 2, up to 5 by week 3, more only after the step 2.5 gate in the plan.

**"Complete" means all of these, or the squad isn't done:**

- code that meets the spec's acceptance commands;
- tests written from the spec, failing before the code and passing after;
- CLI help, docs page or README section updated;
- one `CHANGELOG.md` line;
- bench output before and after, if the feature claims to be faster or cheaper;
- a PR description listing T0/T1 decisions taken, decision cards raised, and open questions.

**Good squad work vs not**

| Give it to a squad | Keep it out of squads |
| --- | --- |
| Lives in one lane's paths (E2 decode, C3 sampling, C7 bench, S4 serve, S6 export, S8 mcp) | Anything marked **(you)** in the backlog |
| Acceptance test is a command with an expected output | Cross-cutting work like the S1 scheduler |
| Interfaces it needs are already merged | Interface or schema changes: do that small PR first, merge it, then launch squads against it. The same holds for specs: plan the interface spec first, then the specs that use it |
| Fits in one PR under about 400 lines | Work two squads would both touch |

**A squad's life**

1. You label the issue `agent-ready`. The lead dispatches a `planner` per issue in parallel (prompt P1), then a `spec-critic` per draft; the planner fixes what the critic found. You approve the spec (gate 1); the lead sets its Status to approved and commits it on local `main`. Builders branch from local HEAD, so they see it, and the spec ships inside the feature's PR.
2. The lead dispatches one `feature-builder` per approved spec, in parallel, each in its own worktree (prompt P2).
3. The builder reads `AGENTS.md` and the spec, asks `test-writer` for tests from the acceptance list, implements until they pass, updates docs and changelog, and runs `make check`.
4. It runs the self-check (prompt P4) and opens a draft PR.
5. The lead dispatches `reviewer` and `test-auditor` in parallel on the PR (P5). It resumes the same builder with SendMessage to fix blocking items in one round (P7); the builder marks the PR ready.
6. You merge (gate 3). The worktree is removed.
7. If anything went badly, run the retro (P10) and approve the context edit (gate 4).

**Three ways to run many agents, and when to use each**

| Tool | Shape of work | Example |
| --- | --- | --- |
| Parallel subagents from the lead session | Different features in parallel, each needing your occasional answer | C3, C7 and S6 in the same week |
| `/batch` in Claude Code | One mechanical change spread across many files; it splits into 5 to 30 worktree-isolated subagents | Add warning codes to every stage; add docstrings to the public API |
| A dynamic workflow ("use a workflow to ...") | Many agents whose findings should be cross-checked before you see them | Audit every stage for per-file error isolation; find flaky tests |

Two traps. A subagent with `isolation: worktree` branches from `worktree.baseRef`; this repo sets `head` in `.claude/settings.json` so builders see approved specs that are committed locally. And the helpers a builder calls (`test-writer`, `fixture-maker`) carry no isolation of their own, so they work inside the builder's worktree; only builders get a worktree.

## Context files

Agents are only as good as the files they read on startup. These replace the v1 `AGENTS.md` in the plan doc. Keep `AGENTS.md` the single source of truth; Claude reads it through `CLAUDE.md`, and it stays readable by any other agent tool you add later.

**`AGENTS.md` (v2, you own it)**

```markdown
# tapesift agent guide
Self-hosted engine: video and audio in, timestamped searchable data out.
Spec: docs/spec.md. Feature specs: docs/specs/. Decisions: docs/adr/.

## Commands
- Setup: uv sync --all-extras
- Everything: make check   (must pass before you say done)
- Fast loop: uv run pytest tests/unit -x -q
- Smoke: uv run pytest tests/smoke -q

## Lanes (edit only your spec's paths)
- Core: src/tapesift/{cli,pipeline,runner,store,audio,vision,serve}/
- Media: src/tapesift/media/, src/tapesift/kernels/, scripts/make_fixtures.py
- Eval: src/tapesift/{eval,safety}/, bench/, evals/
- Train: src/tapesift/train/
- Docs: docs/, README.md, devlog/

## Code rules
- Timestamps come from PTS, in seconds. Never frame_index / fps.
- One bad file never fails a batch: catch per file, record a warning code.
- Typed code; pyright strict passes on src/. No print; use the logger.
- Every network or subprocess call has a timeout.
- New behavior starts with tests from the spec; a bug fix starts with a failing test.

## Decision tiers
- T0 trivial, T1 cheap to reverse: decide; list T1 calls in the PR.
- T2 costly to reverse, T3 one-way door: write a decision card, then stop.

## Stop and raise a decision card before you
- add, remove or upgrade a dependency
- change a public interface, the output schema, a CLI command or flag, or a config key or default
- delete, skip, loosen or rewrite an existing test
- edit outside the paths in your spec
- touch licensing, privacy, security, credentials or training data
- start anything that costs money
- fail the same error twice in a row (write what you tried and your best guess)
- find the spec ambiguous

## Decision card format
### Decision needed (T2 or T3): <one line>
Context / Options A-C with pros and cons / Hardest to reverse /
Recommendation / Would change my mind / Blocked until answered

## Done means
make check green, the spec's acceptance commands pass, docs and CHANGELOG updated.
PR description sections: Summary, How tested (with output), Numbers (perf only),
Decisions (T0/T1), Cards raised, Open questions.
Never push to main, publish, or post. Draft PRs only.
```

**`CLAUDE.md`**: `@AGENTS.md`, plus Claude-only notes: the lead session's fan-out rule (several subagents per step, every time, ADR 0009), helpers stay inside the builder's worktree, the ship-feature skill before any PR, and no Claude co-author trailer. Read the file itself; it is short.

**Subagents** in `.claude/agents/`. `feature-builder` lists plain `Agent` in its tools because type allowlists are ignored inside subagents (ADR 0009); its prompt limits which helpers it spawns. `model: inherit` means the session's model; switch to a named model once you know your token budget.

| File | Model | Isolation | Job |
| --- | --- | --- | --- |
| `planner.md` | opus | none | Issue to spec in `docs/specs/`, nothing else |
| `spec-critic.md` | sonnet | read-only tools | Attacks every draft spec before gate 1 |
| `feature-builder.md` | inherit | `worktree` | One spec to one draft PR, test-first; may spawn only `test-writer` and `fixture-maker` |
| `test-writer.md` | inherit | runs in the builder's worktree | Tests from the acceptance list; never edits `src/` |
| `fixture-maker.md` | inherit | runs in the builder's worktree | Synthetic fixtures via `scripts/make_fixtures.py` |
| `reviewer.md` | opus | read-only by prompt | Bugs, timestamps, bad files, security, spec drift, contract changes |
| `test-auditor.md` | sonnet | read-only by prompt | Missing or weak tests, deleted or skipped tests, unbacked claims |
| `council.md` | set per call (opus, sonnet) | read-only tools | Advice on T3 decisions; never decides |
| `scribe.md` | haiku | write scope in file | ADR drafts, devlog drafts, CHANGELOG lines, metrics, scorecard |

Read the files themselves for the exact prompts; this table is a map, not a copy.

**Skills** in `.claude/skills/<name>/SKILL.md`: short checklists loaded only when needed, which keeps every session's starting context small.

| Skill | What it holds |
| --- | --- |
| `ship-feature` | The 7-step self-check: make check; acceptance output pasted; diff inside spec paths; no test deleted or loosened; docs and CHANGELOG; bench median of 3 for perf claims; draft PR with the required sections |
| `decision-card` | Tier definitions, the card template, two filled examples from this repo |
| `write-adr` | The ADR template and where drafts go |
| `run-bench` | Exact bench commands, how to report median and spread, which machine counts |

**Formatting runs in pre-commit, not in a Claude hook.** Hook paths keep pointing at the main checkout when Claude works in a worktree, while pre-commit runs wherever the commit happens. One less thing to debug.

**Permissions** stay as in the plan doc: allow `make check` and `uv run pytest|ruff|pyright`, ask for `git push`, `gh pr create` and `uv add` until step 2, deny reading `.env` and `uv publish`.

## Prompt library

Copy these as they are. Short prompts work because the rules live in `AGENTS.md`, the subagent files and the spec. If you find yourself writing a long prompt, the missing context belongs in one of those files instead.

| ID | Step | Sent to |
| --- | --- | --- |
| P1 | Write specs | Lead dispatches `planner` per issue, then `spec-critic` per spec, in parallel |
| P2 | Build | Lead dispatches `feature-builder` per approved spec, in parallel |
| P4 | Self-check before PR | The builder |
| P5 | Review a PR | Lead dispatches `reviewer` and `test-auditor`, in parallel |
| P7 | Fix review findings | The same builder, resumed with SendMessage |
| P8 | Council, round 1 | Two `council` subagents (opus, sonnet), separately |
| P9 | Council, round 2 | Each council subagent, resumed with the other's answer |
| P10 | Retro on a bad PR | Lead session |
| P11 | Nightly scribe run | `scribe` subagent |
| P12 | Teach me this PR | Lead session |

P3 and P6 were the Codex build and Codex-review prompts; retired by ADR 0009.

**P1. Specs** (to the lead session)

```text
For issues #<N>, #<M>: dispatch one planner per issue in parallel ("Write the spec for issue
#<N>. Read AGENTS.md, docs/spec.md and the code it touches first."). When each draft lands,
dispatch a spec-critic on it, resume the planner with the critic's findings, and stop when the
critic says "ready for approval". Then show me each spec's path and any decision cards.
```

**P2. Build** (to the lead session, after gate 1)

```text
Set Status: approved in each approved spec and commit them on local main (no push). Then
dispatch one feature-builder per approved spec, in parallel, in the background:
"Build issue #<N> from docs/specs/<N>-<slug>.md." Report each draft PR link and any decision
card as it arrives. Don't answer decision cards yourself.
```

**P4. Self-check** (the builder runs this before its PR; you can also send it if it skipped)

```text
Before opening the PR: run make check and every acceptance command and paste the output.
Show git diff --stat and confirm every file is inside the spec's paths. Confirm no test was
deleted, skipped or loosened. List your T1 decisions in one line each, and anything you're unsure of.
```

**P5. Review** (to the lead session, for each draft PR)

```text
For PR #<P> (spec docs/specs/<N>-<slug>.md): dispatch reviewer and test-auditor in parallel on
its branch. Verify each blocking or should-fix finding yourself before passing it on; drop the
ones you can't reproduce and say why. Then resume the builder with P7 and the surviving list.
```

**P7. Fix findings**

```text
Address the blocking and should-fix items from this review: <paste>. For each item say
"fixed" or "disagree, because ...". Change nothing else. Rerun make check.
```

**P8. Council round 1** (the lead sends the same text to two `council` subagents in parallel, setting the Agent call's `model` to `opus` for one and `sonnet` for the other; council.md has no model of its own so this override decides it)

```text
Decision: <question>. Context: <facts and numbers>. Read AGENTS.md and the relevant code first.
Give 2-3 options with tradeoffs specific to this repo, say which is hardest to reverse, give
your recommendation, and say what evidence would change your mind. Under 250 words.
```

**P9. Council round 2** (the lead resumes each council subagent with the other's answer)

```text
Another engineer answered the same question: <paste>. Where do you disagree, and why?
Change your recommendation only if their argument is better. Under 150 words.
```

**P10. Retro**

```text
PR #<N> needed <k> review rounds / was rejected because <reason>. What context was missing
from AGENTS.md, the spec, a subagent file or a skill that would have prevented it? Propose the
smallest general edit as a diff. Don't apply it.
```

**P11. Scribe**

```text
@agent-scribe Read today's merged PRs, answered decision cards and git log. Draft CHANGELOG
entries, up to 3 devlog posts, ADR drafts for T2/T3 decisions, and update docs/metrics.md.
```

**P12. Teach me this PR** (one a day, out loud, for your own interview prep)

```text
Explain PR #<N> the way a senior engineer onboards a new teammate: the problem, the key design
choice, the alternative rejected and why, and two questions an interviewer could ask about it.
```

## Running it day to day

One lead Claude session in the repo dispatches every subagent and collects their results. Long-running squads run as background subagents; the lead tells you when one is blocked on a card or has opened a PR. herdr is optional: use it to keep the lead session alive across laptop sleeps and for the GPU shell.

**Morning, 20 minutes**

1. Open the lead session (`claude --continue`, or `claude agents` to see background sessions).
2. Answer every decision card the lead surfaced (gate 2).
3. Merge or comment on every draft PR that has its reviewer and test-auditor results (gate 3).
4. Send P1 for one to three `agent-ready` issues and approve the specs (gate 1).
5. Send P2 to launch the squads.

**Evening, 90 minutes**

1. Send P5 for every PR that finished; read the verified findings and the diffs; merge or let P7 run.
2. Run a council (P8, P9) if a T3 card is waiting.
3. Work on your own hand-written piece. No agents touch it.
4. Send P11 to the scribe, then P12 on the day's best PR and say the answer out loud.

**From step 2.5:** the lead picks up `agent-ready` issues itself, runs P1 through P5 end to end, and stops only at your gates. Use `/batch` for wide mechanical changes and dynamic workflows for audits (table above).

**Weekly, Sunday, 30 minutes**

- `git worktree list`, then remove merged ones with `git worktree remove <path>`. Claude cleans up its own clean worktrees on exit.
- Read `docs/metrics.md` (Learning loop section) and decide one change for next week.
- Label next week's `agent-ready` issues, and check each touches only one lane's paths.

## Verification and definition of done

Three layers check every PR, and each catches what the one before it misses. You are the last layer, not the only one.

| Layer | Who | Catches | Time |
| --- | --- | --- | --- |
| 1. Self-check | The builder (`ship-feature`, P4) | Failing tests, scope creep, missing docs, unmeasured speed claims | Minutes, no attention from you |
| 2. Machine gates | CI, security review, `reviewer` + `test-auditor` | Type and lint errors, broken smoke runs, offline failures, bugs and weak tests the builder missed | Minutes, no attention from you |
| 3. You | Gate 3 | Wrong problem solved, bad tradeoffs, weak tests, anything touching data or privacy | 10 to 30 min |

**PR template** (`.github/pull_request_template.md`; every builder fills it):

```markdown
## Summary
## Spec
docs/specs/<N>-<slug>.md
## How tested
<make check result, acceptance command output>
## Numbers (performance work only)
<median of 3, before and after, same machine>
## Decisions (T0/T1)
## Decision cards raised
## Open questions
## Reviewer checklist (you)
- [ ] Does what the spec asked, and nothing else
- [ ] No unapproved dependency, schema, CLI, config or interface change
- [ ] Tests would fail if the code were wrong
- [ ] Behaves on a bad file, a timeout, empty input, a 3-hour input
- [ ] Speed claims have numbers
```

**What you can stop reading as trust grows.** Weeks 1 and 2: read every line. From step 2: skim the implementation of T0/T1 changes when the tests are strong and the reviewer found nothing blocking. Never skip, at any step: the tests, interface and schema diffs, anything touching decode timestamps, privacy, security, credentials or training data.

**Machine checks that make trust cheaper:**

- CI fails if a test file loses tests, or if `@skip` or `xfail` appears in a diff without a decision card number in the same line.
- CI runs the smoke suite on the messy fixtures, so "works on my file" can't pass.
- The offline run (network off after model cache) catches accidental network calls.
- Perf PRs without a `bench.json` diff are marked "needs numbers" by a small CI check.

## Failure modes and fixes

Most agent failures are context failures. Fix the file that was missing the context, not just the one PR.

| Symptom | Usual cause | Fix |
| --- | --- | --- |
| Agent retries the same error for an hour | No loop guard | The two-failures stop rule; give it the error plus your hypothesis |
| Tests edited until they pass | Nothing stops it | Stop rule, the CI test-count check, reviewer reads test diffs first |
| PR does more than asked | Spec without scope paths | Planner must fill "paths you may change"; reviewer flags drift as should-fix |
| Two PRs conflict | Two squads share paths | Lanes by path; interface PR merged before squads start |
| "3x faster" with no proof | No measurement rule | `run-bench` skill; CI marks perf PRs without `bench.json` |
| Calls a library function that doesn't exist | Stale knowledge of the library | Pin versions; tell it to read the installed package's source; add a note to `AGENTS.md` |
| Sessions get slow and forgetful | One session doing many features | One feature per session; fresh session per issue; skills instead of a long `CLAUDE.md` |
| Usage limit hit by Wednesday | Too many agents, too much effort setting | Scribe on haiku; review trivial PRs with a smaller model; workflow size guideline small; fewer squads |
| reviewer and test-auditor disagree | Normal, and useful | You decide; log who was right in `docs/metrics.md` |
| A subagent goes quiet | Waiting on a permission or a decision card | The lead surfaces it; clear blocked agents first, every time |
| Flaky tests | Nondeterminism | Fix flakes before adding agents; seeds fixed; one dynamic workflow to hunt them |
| An agent "decides" a T3 question | Tier not obvious from the card rules | Add the example to the `decision-card` skill; revert and rerun with a card |

**The habit that matters most:** when the same review comment appears twice, it becomes a line in `AGENTS.md` or a skill. When you catch the same bug twice by hand, it becomes a CI check.

## Learning loop and the numbers to track

The scribe updates `docs/metrics.md` nightly from git and PR history; you read it on Sundays. These numbers decide which tool gets which lane and when you add more agents.

| Number | Healthy sign | If it's off |
| --- | --- | --- |
| PRs merged per week | Rising for 3 weeks | Check if review is your bottleneck; shrink specs |
| Merged without you editing code | 70%+ by step 2 | Read the retros; the missing context is in a pattern |
| Review rounds per PR | 1 to 2 | Specs too vague, or `AGENTS.md` missing a rule |
| Bugs caught, by reviewer vs test-auditor vs CI vs you | CI and reviewers catch most | Move what you catch by hand into CI |
| Decision cards per week, and your override rate | Few T2/T3 cards; overrides falling | High overrides: agents lack context; zero cards: they're deciding things they shouldn't |
| Issue-to-merge time | Under 2 days for squad work | Look for PRs waiting on you, not on agents |
| Bugs found after merge | Near zero | Add a test category or a CI check for each one |
| Usage spent per merged PR | Flat or falling | Smaller models for scribe and trivial reviews; fewer parallel squads |

**Model swaps.** After about 10 merged PRs, compare reviewer findings that held up against test-auditor's and against what you caught. Move a role to a bigger or smaller model when the numbers say so, and write it as an ADR. If you keep catching bugs both reviewers missed, ADR 0009 says to add a second-vendor reviewer.

**When to add agents.** Only when merged-without-edits is above 70% and your review time per PR is falling. More agents before that means more broken PRs waiting for you.

**Your own growth, on purpose:**

- Predict, then compare, on every decision card (Decision protocol section). The scorecard shows where your judgment is ahead of or behind the models'.
- P12 every day, answered out loud. Those answers become interview material and vlog clips.
- The four hand-written pieces stay yours: the scheduler core, the Triton dedupe kernel, the tIoU metric, the reward functions.
- Once a month, reread the ADRs and mark which held up. That's how you learn which kinds of decisions you get wrong.

## Sources

Commands and frontmatter fields were checked against these pages on Oct 13, 2026. If a flag errors, run the tool's `--help`; agent CLIs change monthly.

- [Claude Code: Create custom subagents](https://code.claude.com/docs/en/sub-agents): frontmatter fields (`tools`, `disallowedTools`, `model`, `permissionMode`, `isolation`, `skills`, `effort`), `@agent-<name>`, `claude --agent`, `Agent(...)` restrictions, nesting depth, 20 concurrent subagents by default
- [Claude Code: Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees): `--worktree`, subagent worktrees branch from `worktree.baseRef` (`fresh` = remote default branch, `head` = local HEAD), hook paths stay on the main checkout
- [Claude Code: Run agents in parallel](https://code.claude.com/docs/en/agents): agent view, `/batch`, routines
- [Claude Code: Dynamic workflows](https://code.claude.com/docs/en/workflows): when a workflow beats subagents, size guideline
- [Claude Code: Configure auto mode](https://code.claude.com/docs/en/auto-mode-config): ask and deny rules that hold in auto mode
- [Claude Code: Create custom subagents](https://code.claude.com/docs/en/sub-agents), rechecked Oct 16, 2026 for ADR 0009: subagents nest up to three layers; `Agent(type)` allowlists are ignored inside subagent definitions; finished subagents resume with SendMessage
- [Steps of AI Adoption](https://claude.ai/code/artifact/bfdfaef9-bc62-4dfe-ba9e-c58a26c9accf), Boris Cherny: the step 1 to 3 ladder this workflow builds toward
- [Build plan](https://claude.ai/code/artifact/2af96e92-7faf-4aa5-b828-ff39efedfac1): lanes, backlog, permissions and the step gates this doc runs on
