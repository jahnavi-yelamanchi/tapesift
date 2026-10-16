# tapesift Agentic Workflow

Oct 13, 2026 · @jahnavi

## Operating model

You decide and review; Claude and Codex build and check each other's work. Every feature goes around the same loop, and you appear at four gates. This doc defines the roles, files, prompts and commands that make the loop run. The [build plan](https://claude.ai/code/artifact/2af96e92-7faf-4aa5-b828-ff39efedfac1) says what to build; this doc says how.

&#91;embedded content: build loop · 7 steps, 4 human gates\]

The loop closes through gate 4: each retro edits the files every agent reads at startup, so the next feature starts with the lesson already built in.

## Roles

One model builds, the other reviews; on hard decisions both advise and you decide. Which tool plays which role is a starting guess: track results (Learning loop section) and swap after about 10 PRs per lane.

| Role | Played by | Owns | Never does |
| --- | --- | --- | --- |
| Tech lead | You | Specs you approve, decisions, merges, the four hand-written pieces, posts | Merges a PR without reading its tests and interface changes |
| Planner | Claude Code, `planner` subagent, Opus | Turns an issue into a spec, a task list and decision cards | Writes product code |
| Feature builder | Claude Code `feature-builder` in its own worktree, or Codex in its own worktree | One complete feature: tests, code, docs, changelog line, PR | Adds dependencies, changes interfaces, or edits outside its scope without a decision card |
| Test writer | Claude Code `test-writer` subagent, called by a builder | Tests written from the spec, before or alongside code | Edits `src/` |
| Fixture maker | Claude Code `fixture-maker` subagent | Synthetic messy-data fixtures | Uses real or unlicensed footage |
| Reviewer | The model that didn't build: `codex review` on Claude PRs, Claude `reviewer` on Codex PRs | Bugs, missing tests, spec drift, risky changes | Edits code |
| Council | Claude and Codex, asked separately | Options and a recommendation on one-way-door decisions | Decides |
| Scribe | Claude Code `scribe` subagent, small model | ADR drafts, changelog lines, devlog drafts, metrics | Posts, merges or pushes anything |

**Starting lane assignment** (from the plan): Claude builds Core, Train and Docs; Codex builds Media and Eval. Codex is strong on self-contained modules with sharp tests; Claude handles cross-cutting work and runs the subagents. Treat both claims as hypotheses your metrics will confirm or overturn.

## Human checkpoints and stop rules

You step in at four gates and nowhere else. Implementing, testing, fixing lint, opening PRs, reviewing and retrying CI all run without you.

| Gate | When | What you check | Time |
| --- | --- | --- | --- |
| 1. Approve spec | Before any code | Goal, acceptance commands, interfaces touched; the plan too if an interface, schema, CLI flag, config key or dependency changes | 5 to 10 min |
| 2. Decide | Whenever an agent raises a decision card | The options and the recommendation (Decision protocol section) | 2 to 15 min |
| 3. Merge | CI green and cross-review done | Tests first, then interface changes, then behavior on bad input | 10 to 30 min |
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

How stopping looks in practice: a Codex pane or Claude session shows **blocked** in the herdr sidebar with the card as its last message. A background Claude subagent's question surfaces in its parent session. Nothing waits silently.

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

1. Ask Claude and Codex the same question in separate sessions (prompt P8). Neither sees the other's answer.
2. Paste each answer to the other and ask for a rebuttal (prompt P9).
3. You decide. If both agree and you disagree, write down why; that's either a lesson for you or a gap in their context.
4. The scribe drafts the ADR, including the option you rejected and the strongest argument for it.

**How this teaches you judgment:** before you read an agent's recommendation, write your own pick and one-line reason in the card. Then compare. Over a month, the cases where you and the agents disagreed, and who turned out right, are the most useful senior-engineering lessons in this project. The scribe logs them in `docs/decisions-scorecard.md`.

## Feature squads

A feature squad is one builder that takes one approved spec all the way to a ready PR, alone, in its own worktree. Run 2 squads at once in weeks 1 and 2, then up to 5 by week 3, and more only after the step 2.5 gate in the plan.

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
| Interfaces it needs are already merged | Interface or schema changes: do that small PR first, merge it, then launch squads against it |
| Fits in one PR under about 400 lines | Work two squads would both touch |

**A squad's life**

1. You label the issue `agent-ready`. The planner writes `docs/specs/<id>-<slug>.md` (prompt P1). You approve it (gate 1).
2. You launch the builder in its own worktree: Claude with `claude --agent feature-builder --worktree s8-mcp`, or Codex through herdr (commands in Running it day to day).
3. The builder reads `AGENTS.md` and the spec, asks `test-writer` for tests from the acceptance list, implements until they pass, updates docs and changelog, and runs `make check`.
4. It runs the self-check (prompt P4) and opens a draft PR.
5. The other model reviews (P5 or P6). The builder fixes blocking items in one round (P7) and marks the PR ready.
6. You merge (gate 3). The worktree is removed.
7. If anything went badly, run the retro (P10) and approve the context edit (gate 4).

**Three ways to run many agents, and when to use each**

| Tool | Shape of work | Example |
| --- | --- | --- |
| herdr panes, one squad per pane | Different features in parallel, each needing your occasional answer | C3, C7 and S6 in the same week |
| `/batch` in Claude Code | One mechanical change spread across many files; it splits into 5 to 30 worktree-isolated subagents | Add warning codes to every stage; add docstrings to the public API |
| A dynamic workflow ("use a workflow to ...") | Many agents whose findings should be cross-checked before you see them | Audit every stage for per-file error isolation; find flaky tests |

One trap: a subagent with `isolation: worktree` branches from `main`, not from the builder's branch. So the helpers a builder calls (`test-writer`, `fixture-maker`) run without worktree isolation, inside the builder's own worktree. Only standalone squads get their own worktree.

## Context files

Agents are only as good as the files they read on startup. These replace the v1 `AGENTS.md` in the plan doc. Keep `AGENTS.md` the single source of truth: Codex reads it from the repo root down to the folder it starts in (plus your global `~/.codex/AGENTS.md`), and Claude reads it through `CLAUDE.md`.

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

**`CLAUDE.md`**

```markdown
@AGENTS.md

## Claude Code only
- planner writes specs; test-writer writes tests; fixture-maker makes fixtures.
- Helpers you call during a feature work inside your worktree; never give them their own.
- Use the ship-feature skill before opening any PR.
```

**Subagents** in `.claude/agents/`. `model: inherit` means the session's model; switch to a named model once you know your token budget.

`feature-builder.md`

```markdown
---
name: feature-builder
description: Builds one complete feature from an approved spec in docs/specs/, test-first, and opens a draft PR. Use for issues labeled agent-ready.
tools: Agent(test-writer, fixture-maker), Read, Edit, Write, Glob, Grep, Bash
model: inherit
permissionMode: auto
effort: high
skills: [ship-feature]
---
You build exactly one feature, end to end.
1. Read AGENTS.md and your spec. Restate the goal and acceptance commands in 3 lines.
2. Ask test-writer for tests covering every acceptance command. Confirm they fail.
3. Implement the smallest change that passes them, inside the spec's paths.
4. Update CLI help or docs, and add one CHANGELOG line.
5. Run make check and every acceptance command until green.
6. Follow ship-feature, then open a draft PR.
Any T2/T3 choice or stop rule from AGENTS.md: write the decision card and stop.
```

`planner.md`

```markdown
---
name: planner
description: Turns an issue into a feature spec with acceptance commands, interfaces touched and decision cards. Use before any feature work.
tools: Read, Glob, Grep, Write, Bash, WebSearch, WebFetch
model: opus
effort: high
---
Write docs/specs/<issue>-<slug>.md and nothing else. Sections: Goal; Read first;
Scope (paths you may change, paths you must not touch); Interfaces touched (exact
signatures); Acceptance (commands and expected output); Out of scope; Risks;
Decision cards for every T2/T3 choice. Read the code before proposing interfaces.
Propose the smallest feature that meets the goal.
```

`reviewer.md`

```markdown
---
name: reviewer
description: Read-only review of a branch or PR against its spec. Use on every PR Codex builds.
tools: Read, Glob, Grep, Bash
disallowedTools: Edit, Write
model: inherit
---
Compare the diff to its spec in docs/specs/. Report in this order, citing file and line:
1. Blocking: bugs, wrong timestamps, crashes on bad files, security or privacy issues.
2. Should fix: missing tests, tests that would pass with broken code, spec drift.
3. Contract changes: dependency, schema, CLI, config or interface changes.
4. Claims without evidence: speedups without bench output.
5. Questions.
No style nits unless they hide a bug. Say "nothing blocking" when true.
```

`test-writer.md`, `fixture-maker.md`, `scribe.md` (short; same frontmatter shape)

```markdown
---
name: test-writer
description: Writes tests from a spec's acceptance list before implementation. Called by feature-builder.
tools: Read, Glob, Grep, Edit, Write, Bash
---
Write tests in tests/ only, one per acceptance item plus the messy-data edge cases that apply.
Use hypothesis for timestamp and metric math. Confirm they fail for the right reason. Never edit src/.

---
name: fixture-maker
description: Adds a synthetic messy-data fixture to scripts/make_fixtures.py. Called by feature-builder.
tools: Read, Edit, Write, Bash
---
Generate fixtures only from FFmpeg test sources. Keep all fixtures under 5 MB. Never use real footage.

---
name: scribe
description: Drafts ADRs, CHANGELOG lines, devlog posts and the weekly metrics table from git history. Never posts or merges.
tools: Read, Glob, Grep, Write, Bash
model: haiku
---
Write only under docs/adr/drafts/, devlog/drafts/ and docs/metrics.md.
```

(Each is its own file; they're shown together here to save space.)

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
| P1 | Write a spec | Claude `planner` |
| P2 | Build (Claude) | `feature-builder` session |
| P3 | Build (Codex) | Codex in its worktree |
| P4 | Self-check before PR | Either builder |
| P5 | Review a Claude PR | Codex |
| P6 | Review a Codex PR | Claude `reviewer` |
| P7 | Fix review findings | The builder |
| P8 | Council, round 1 | Claude and Codex, separately |
| P9 | Council, round 2 | Each, with the other's answer |
| P10 | Retro on a bad PR | Claude, in the lead pane |
| P11 | Nightly scribe run | Claude `scribe` |
| P12 | Teach me this PR | Either |

**P1. Spec**

```text
@agent-planner Write the spec for issue #<N>. Read AGENTS.md, docs/spec.md and the code it touches first.
```

**P2. Build with Claude** (launched as `claude --agent feature-builder --worktree <id>-<slug>`)

```text
Build issue #<N> from docs/specs/<N>-<slug>.md.
```

**P3. Build with Codex**

```text
Build issue #<N> from docs/specs/<N>-<slug>.md. Follow AGENTS.md exactly: tests from the
acceptance list first, then code, then docs and CHANGELOG. Run make check and the acceptance
commands until green, then open a draft PR with gh using the sections AGENTS.md lists.
For any T2/T3 choice or stop rule, write the decision card and stop.
```

**P4. Self-check** (the builder runs this before its PR; you can also send it if it skipped)

```text
Before opening the PR: run make check and every acceptance command and paste the output.
Show git diff --stat and confirm every file is inside the spec's paths. Confirm no test was
deleted, skipped or loosened. List your T1 decisions in one line each, and anything you're unsure of.
```

**P5. Codex reviews a Claude PR** (run inside that PR's worktree)

```text
codex review --base main
```

If it needs steering, start `codex` in the worktree and send: "Review this branch against docs/specs/\<N>-\<slug>.md. Report blocking bugs, missing or weak tests, spec drift, contract changes (dependency, schema, CLI, config, interface), and speed claims without numbers. Cite file and line. No style nits."

**P6. Claude reviews a Codex PR**

```text
@agent-reviewer Review branch <branch> against docs/specs/<N>-<slug>.md.
```

**P7. Fix findings**

```text
Address the blocking and should-fix items from this review: <paste>. For each item say
"fixed" or "disagree, because ...". Change nothing else. Rerun make check.
```

**P8. Council round 1** (same text to each model, in separate sessions)

```text
Decision: <question>. Context: <facts and numbers>. Read AGENTS.md and the relevant code first.
Give 2-3 options with tradeoffs specific to this repo, say which is hardest to reverse, give
your recommendation, and say what evidence would change your mind. Under 250 words.
```

**P9. Council round 2**

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

One herdr workspace holds every agent. The sidebar shows each one as blocked, working, done or idle. Your whole job between work blocks is to clear **blocked** first, review **done** next, and leave **working** alone. Pane IDs such as `w1:p3` show in the sidebar.

**Once**

```bash
herdr workspace create --cwd ~/code/tapesift --label tapesift
```

**Morning, 20 minutes**

1. Run `herdr` to reattach. Everything kept running overnight.
2. Answer every decision card on a **blocked** pane (gate 2).
3. Merge or comment on every **done** PR that has its cross-review (gate 3).
4. In the `lead` pane, send P1 for one to three `agent-ready` issues and approve the specs (gate 1).
5. Launch the squads:

```bash
# a Claude squad: the session itself is the feature-builder, in its own worktree
herdr pane split --current --direction right --no-focus
herdr pane run w1:p2 "claude --agent feature-builder --worktree s8-mcp 'Build issue #41 from docs/specs/41-mcp.md.'"

# a Codex squad: make the worktree, start Codex in it, send P3 and wait
git worktree add ../tapesift-wt/c7-bench -b feat/c7-bench
herdr agent start c7 --kind codex --pane w1:p3 -- -C ../tapesift-wt/c7-bench --sandbox workspace-write -a on-request
herdr agent prompt c7 "<P3 for issue #31>"
```

**Evening, 90 minutes**

1. Cross-review whatever finished: Codex on Claude branches, Claude's reviewer on Codex branches.

```bash
herdr pane run w1:p5 "cd .claude/worktrees/s8-mcp && codex review --base main"
```

2. Read the reviews and the diffs; merge or send P7.
3. Run a council (P8, P9) if a T3 card is waiting.
4. Work on your own hand-written piece. No agents touch it.
5. Send P11 to the scribe, then P12 on the day's best PR and say the answer out loud.

**From step 2.5: Claude as the orchestrator.** With the herdr skill installed, Claude in the `lead` pane can start and watch the squads for you:

```text
Using herdr in workspace tapesift: start one squad each for #31 (Codex, Media lane)
and #33 and #41 (Claude feature-builder, Core lane), each in its own worktree and pane.
Wait until each is blocked or done. Then give me a table: issue, agent, status, PR link,
decision cards waiting. Don't answer decision cards yourself.
```

Underneath, it uses the same commands you would: `herdr agent start`, `herdr agent prompt ... --wait`, `herdr agent wait <name> --until blocked --until done`, and `herdr agent read <name> --source recent-unwrapped --lines 120` to collect the results.

For Claude-only work you can also dispatch background sessions from `claude agents` (agent view). herdr stays the main screen because it shows Claude and Codex side by side.

**Weekly, Sunday, 30 minutes**

- `git worktree list`, then remove merged ones with `git worktree remove <path>`. Claude cleans up its own clean worktrees on exit.
- Read `docs/metrics.md` (Learning loop section) and decide one change for next week.
- Label next week's `agent-ready` issues, and check each touches only one lane's paths.

## Verification and definition of done

Three layers check every PR, and each catches what the one before it misses. You are the last layer, not the only one.

| Layer | Who | Catches | Time |
| --- | --- | --- | --- |
| 1. Self-check | The builder (`ship-feature`, P4) | Failing tests, scope creep, missing docs, unmeasured speed claims | Minutes, no attention from you |
| 2. Machine gates | CI, security review, the other model's review | Type and lint errors, broken smoke runs, offline failures, bugs one model misses | Minutes, no attention from you |
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
| Claude and Codex reviews disagree | Normal, and useful | You decide; log who was right in `docs/metrics.md` |
| A pane sits idle with no output | Waiting on a permission or a question | It shows as blocked in herdr; clear blocked panes first, every time |
| Flaky tests | Nondeterminism | Fix flakes before adding agents; seeds fixed; one dynamic workflow to hunt them |
| An agent "decides" a T3 question | Tier not obvious from the card rules | Add the example to the `decision-card` skill; revert and rerun with a card |

**The habit that matters most:** when the same review comment appears twice, it becomes a line in `AGENTS.md` or a skill. When you catch the same bug twice by hand, it becomes a CI check.

## Learning loop and the numbers to track

The scribe updates `docs/metrics.md` nightly from git and PR history; you read it on Sundays. These numbers decide which tool gets which lane and when you add more agents.

| Number | Healthy sign | If it's off |
| --- | --- | --- |
| PRs merged per week, by tool | Rising for 3 weeks | Check if review is your bottleneck; shrink specs |
| Merged without you editing code, by tool | 70%+ by step 2 | Read the retros; the missing context is in a pattern |
| Review rounds per PR | 1 to 2 | Specs too vague, or `AGENTS.md` missing a rule |
| Bugs caught, by Claude review vs Codex review vs CI vs you | CI and reviewers catch most | Move what you catch by hand into CI |
| Decision cards per week, and your override rate | Few T2/T3 cards; overrides falling | High overrides: agents lack context; zero cards: they're deciding things they shouldn't |
| Issue-to-merge time | Under 2 days for squad work | Look for PRs waiting on you, not on agents |
| Bugs found after merge | Near zero | Add a test category or a CI check for each one |
| Usage spent per merged PR | Flat or falling | Smaller models for scribe and trivial reviews; fewer parallel squads |

**Lane swaps.** After about 10 merged PRs in a lane, compare the two tools on merged-without-edits and review rounds. If one is clearly better, give it the lane. Write it as an ADR so the post about it has a reason and a number.

**When to add agents.** Only when merged-without-edits is above 70% and your review time per PR is falling. More agents before that means more broken PRs waiting for you.

**Your own growth, on purpose:**

- Predict, then compare, on every decision card (Decision protocol section). The scorecard shows where your judgment is ahead of or behind the models'.
- P12 every day, answered out loud. Those answers become interview material and vlog clips.
- The four hand-written pieces stay yours: the scheduler core, the Triton dedupe kernel, the tIoU metric, the reward functions.
- Once a month, reread the ADRs and mark which held up. That's how you learn which kinds of decisions you get wrong.

## Sources

Commands and frontmatter fields were checked against these pages on Oct 13, 2026. If a flag errors, run the tool's `--help`; agent CLIs change monthly.

- [Claude Code: Create custom subagents](https://code.claude.com/docs/en/sub-agents): frontmatter fields (`tools`, `disallowedTools`, `model`, `permissionMode`, `isolation`, `skills`, `effort`), `@agent-<name>`, `claude --agent`, `Agent(...)` restrictions, nesting depth, 20 concurrent subagents by default
- [Claude Code: Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees): `--worktree`, subagent worktrees branch from the default branch, hook paths stay on the main checkout
- [Claude Code: Run agents in parallel](https://code.claude.com/docs/en/agents): agent view, `/batch`, routines
- [Claude Code: Dynamic workflows](https://code.claude.com/docs/en/workflows): when a workflow beats subagents, size guideline
- [Claude Code: Configure auto mode](https://code.claude.com/docs/en/auto-mode-config): ask and deny rules that hold in auto mode
- [Codex CLI command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli): `-C`, `--sandbox`, `-a`, `codex exec`, `codex review --base`
- [herdr agent automation](https://herdr.dev/docs/agent-automation/): `herdr agent start`, `prompt`, `wait`, `read`, `pane run`, `pane split`, `workspace create`
- [Steps of AI Adoption](https://claude.ai/code/artifact/bfdfaef9-bc62-4dfe-ba9e-c58a26c9accf), Boris Cherny: the step 1 to 3 ladder this workflow builds toward
- [Build plan](https://claude.ai/code/artifact/2af96e92-7faf-4aa5-b828-ff39efedfac1): lanes, backlog, permissions and the step gates this doc runs on
