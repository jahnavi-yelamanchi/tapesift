# tapesift status

As of 2026-10-20. Rewritten in place by the scribe each run. Read this first; the links hold the detail.

## 1. Where we are

- Phase 0 (setup) is closed. The engine phase ([ADR 0001](adr/0001-three-phase-build.md), Oct 14 to Dec 6) is in progress.
- **v0.1 "works on your laptop" is in progress.** Runs Oct 19 to Nov 1. Goal: point tapesift at a 10-minute talk on a laptop-class CPU and search it.
- `origin/main` is at 3a93cf8: #34 (#21, safe opener) merged 2026-10-20. #34 adds 70 tests; main has 521 tests, per the PR report.
- Shipped in #34: every media file opens through a checked file descriptor. Nine containers are allowed. FIFOs and devices are refused. Mutation check: 16 of 19 injected bugs caught; the 3 misses are equivalent code.
- Local `main` has one commit ahead of origin: `2c6dc88`, the approved M1 interface spec ([docs/specs/25-m1-interfaces.md](specs/25-m1-interfaces.md) at that commit). It is not pushed. It goes in through a PR.
- Q1 (torch in the base install) was decided 2026-10-19 by the owner, on install size, after measurement. Base install stays speech and text search. Captions go in `tapesift[vision]`. Writeup on branch `exp/q1-install-timing` (kept, not merged).
- Draft PR: `docs: v0.1 decisions (ADR 0013 draft), devlogs, status` (this run). Nothing merged by this run.

## 2. What is running

- **M1 (#25), interfaces.** Spec approved 2026-10-20 (commit `2c6dc88`). Builder in progress, per the session log. No M1 PR is open on GitHub yet.
- **E3 to E8 specs.** Being planned in parallel, per the session log. Issues #26 to #31 are open. Waves follow M1 (see section 8).
- No other builders. No open PRs other than this docs draft.

## 3. How we work

Claude Code subagents only, several per step ([ADR 0009](adr/0009-claude-only-subagents.md)). Planner and spec-critic write and attack each spec. Parallel feature-builders each work in their own worktree. Reviewer and test-auditor run on every PR. Two-model council (one opus seat, one sonnet seat, then a rebuttal round) argues every one-way door. Scribe handles bookkeeping. The owner gates spec approval, decisions, merges and context edits ([workflow](workflow.md)).

Publish rule: nothing is posted or pushed to `main` without the owner. Postable tweets sit in the devlog drafts.

## 4. Decisions

Decided by: owner, plan default, or owner after council.

| ID | Decision | Decided by | Link |
| --- | --- | --- | --- |
| ADR 0001 | Build in three phases: engine, evals and post-training, self-training | owner | [0001](adr/0001-three-phase-build.md) |
| ADR 0002 | tapesift starts and stops vLLM itself on NVIDIA GPUs | owner (plan) | [0002](adr/0002-managed-vllm.md) |
| ADR 0003 | Add `tapesift mcp` in v0.3 | owner (plan) | [0003](adr/0003-mcp-server.md) |
| ADR 0004 | Name tapesift, Apache-2.0; private until launch (amended) | plan defaults D1, D3, D11 | [0004](adr/0004-name-license-public.md) |
| ADR 0005 | Python floor 3.11 (superseded by 0011) | plan default | [0005](adr/0005-python-floor.md) |
| ADR 0006 | Messy-data fixtures are small synthetic files, committed | plan default D7 | [0006](adr/0006-test-fixtures.md) |
| ADR 0007 | Speech fixture synthesized with espeak-ng | owner | [0007](adr/0007-speech-fixtures-espeak.md) |
| ADR 0008 | Laptop only builds code; models, datasets and training run in the cloud | owner | [0008](adr/0008-laptop-builds-cloud-computes.md) |
| ADR 0009 | Claude Code subagents only, several per step; Codex dropped | owner | [0009](adr/0009-claude-only-subagents.md) |
| ADR 0010 | English only in v1.0 | owner | [0010](adr/0010-english-only.md) |
| ADR 0011 | Python floor 3.12 (supersedes 0005) | owner | [0011](adr/0011-python-floor-3-12.md) |
| ADR 0012 | Asset IDs: versioned `tsid1:` head/tail hash; full `sha256:` on request | owner after council | [0012](adr/0012-asset-id-scheme.md) |
| ADR 0013 (draft) | v0.1 decisions: Q1 to Q11, #21 cards, M1 cards 1 to 10 | owner (Q1 to Q11 on 2026-10-19 and 2026-10-20; M1 on 2026-10-20) | [draft](adr/drafts/0013-v01-decisions.md) |
| Spec 21 | Safe opener: 7 cards, all recommended options | owner, 2026-10-19 | [21-safe-opener](specs/21-safe-opener.md) |
| Spec 25 | M1: 10 cards. Cards 1 to 7 T3 (council), 8 to 10 T2 | owner, 2026-10-20 (commit `2c6dc88`, local main) | [25-m1-interfaces](specs/25-m1-interfaces.md) at `2c6dc88` |
| Q1 | Captions in `tapesift[vision]`, not the base install | owner, 2026-10-19, on install size after measurement | [ADR 0013](adr/drafts/0013-v01-decisions.md); branch `exp/q1-install-timing`, `docs/experiments/2026-10-19-q1-install-timing.md` |
| Q9 | Repo public on or before Oct 31; then v0.1.0 to PyPI | owner | [ADR 0013](adr/drafts/0013-v01-decisions.md) |
| M1 card 7 | Guarded num2words shim; no LGPL package ships | owner after council | [ADR 0013](adr/drafts/0013-v01-decisions.md) (M1-7) |
| M0 | Shared media types, records, decode callbacks (6 rows) | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| E1 | HDR detection: probe opens the codec context and decodes no frames | owner, 2026-10-17 | [5-probe](specs/5-probe.md) |
| Repo | `main` takes changes only through a PR; admins included; 5 required checks | owner, 2026-10-18 | [devlog](../devlog/drafts/2026-10-18.md) |

Scorecard for the council calls: [decisions-scorecard.md](decisions-scorecard.md). "My pick" is blank for the owner (#16).

## 5. Lessons

- Parallel planners on interdependent specs diverged. Fix: write the interface spec first (retro rule; M1 is the first use).
- Council rebuttals changed a seat on the M0 `duration_s` data-loss bug, on the `tsid1` prefix (ADR 0012), and on the M1 licensing card (card 7). On the M1 config card, the rebuttal moved the sonnet seat on both splits; the opus seat adopted sonnet's per-profile `max_batch`.
- A builder's test passed on old code in an earlier PR. A mutation run caught it. In #34 the test-auditor ran 19 injected bugs: 16 caught.
- A plan rule was not applied as written for Q1. The rule said option B only if Linux took over 2 minutes; Linux took 33 s. The owner chose B on install size. The ADR says so.
- Two postable claims were checked against the log before posting. One draft tweet had the council numbers wrong and was rewritten.
- Check reviewer suggestions against the spec first (a `start_offset` suggestion on #22 was wrong).

## 6. Waiting on the owner

- **Talk URL and 5 queries** for X1 (Q6, CC BY talk with slides). Needed by about Oct 28. Owner writes `evals/v0.1-talk.toml`: URL, sha256, license, and 5 queries with the expected second.
- **Public flip** on or before Oct 31 (Q9). Then the PyPI pending publishers (TestPyPI and PyPI) and a protected `pypi` environment for E8. A PyPI upload makes the source public for good.
- **Scorecard "My pick"** before reading agent picks (#16). Blank rows: ADR 0007, ADR 0011, ADR 0012, and the seven M1 council rows.
- **Merge the draft PR** `docs: v0.1 decisions (ADR 0013 draft), devlogs, status`. Then decide when to move ADR 0013 from `docs/adr/drafts/` to `docs/adr/` as accepted.
- **Push and merge the M1 spec** (`2c6dc88` on local main) through a PR, with the M1 builder's PR after it.
- **Retro proposals** from [the Phase 0 retro](../devlog/drafts/2026-10-18-phase-0-retro.md#proposed-changes-for-the-owner-to-approve). Still open; Q11 touches proposal (iii).
- **Local clean-up.** Two old worktrees (the #21 builder and the Q1 experiment) and branch `backup/local-spec-21` are on disk. Waiting on "ok clean worktrees".

## 7. Open follow-ups

From `gh issue list --label follow-up` (open, 2026-10-20):
- #11 E7: confirm DUPLICATE with a full hash; never mix ID modes in one index. Replaced by E7 (#30).
- #13 E3: handle audio chunk seams (600 s AudioChunks). Replaced by E3 (#26).
- #14 E5: AssetInfo to output schema mapper; license; rotation and duration semantics. Replaced by E5 (#28).
- #15 C3: CROPPED (letterbox and pillarbox detection). v0.2.
- #16 Decisions scorecard: owner fills "My pick" before reading agent picks.
- #35 Decode: warning details leak the full file path. Older issue; not caused by #34.
- #36 Runner: wall-clock limit per file that kills a stuck worker. A read stuck in the kernel (a dead network mount) stays unbounded until this lands. Core lane, E7 area.

Other open: #9 Media: deinterlace (bwdif) and HDR tone mapping at decode (brief; v0.2). v0.1 issues #25 to #33 are open (M1, E3 to E9, X1).

Closed: #21 (merged in #34).

## 8. Next

Wave plan (from the v0.1 plan; dates are targets):
1. **M1 (#25)** merges first. It is the only PR that adds v0.1 dependencies. Exact pins and lane edit are in the spec.
2. **Wave 2: E3 to E8 in parallel,** up to 6 builders once M1 merges (Q11). Each builder edits only its spec's paths. No E-brief edits `pyproject.toml` or `uv.lock`.
3. **X1 (#33):** the talk check on Modal. Needs the owner's URL and queries.
4. **E9 (#32):** README quickstart and demo GIF (recorded on a laptop-sized Modal CPU box).
5. **Release:** feature freeze Wed Oct 28; install tests, talk check and README Oct 29 to 31; public flip on or before Oct 31; `v0.1.0rc1` to TestPyPI, then `v0.1.0` to PyPI.

Exit criteria: spec 333 as amended by Q7 (laptop-class CPU check), and the WER bound of 0.20 on `speech.mp4` (Q8).
