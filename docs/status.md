# tapesift status

As of 2026-10-20. Rewritten in place by the scribe each run. Read this first; the links hold the detail.

## 1. Where we are

- **Phase: v0.1 lean build.** Runs Oct 19 to Nov 1. Goal: index and search general video on a laptop-class CPU, with a web UI. The MVP is general video only. Lean mode is in force until the MVP demo works ([ADR 0014](adr/drafts/0014-lean-mode-ui-robotics.md), owner, 2026-10-20).
- The engine phase ([ADR 0001](adr/0001-three-phase-build.md), Oct 14 to Dec 6) is in progress. Phase 0 is closed.
- `origin/main` is at 5be28a6 (docs #37, after M1 #38 and #34). Open PRs: this run's draft only.
- **Not yet true:** the product cannot index or search a video end to end. Audio (E3), captions (E4) and search (E6) are not on main.

## 2. Done

| Item | What | Link |
| --- | --- | --- |
| Phase 0 | Setup, repo rules, quickstart; closed 2026-10-18 | [#23](https://github.com/jahnavi-yelamanchi/tapesift/pull/23), [#24](https://github.com/jahnavi-yelamanchi/tapesift/pull/24) |
| #21 Safe opener | Every media file opens through a checked fd; 9 containers; FIFOs and devices refused. 16 of 19 injected bugs caught (3 equivalent) | [#34](https://github.com/jahnavi-yelamanchi/tapesift/pull/34), [spec 21](specs/21-safe-opener.md) |
| M1 interfaces (#25) | Records, ASR/VAD/VLM/Embedder/Store protocols, config, fakes, dependencies | [#38](https://github.com/jahnavi-yelamanchi/tapesift/pull/38), [spec 25](specs/25-m1-interfaces.md) |
| v0.1 decisions (#37) | ADR 0013 draft: Q1 to Q11, #21 cards, M1 cards 1 to 10 | [#37](https://github.com/jahnavi-yelamanchi/tapesift/pull/37), [ADR 0013 draft](adr/drafts/0013-v01-decisions.md) |
| Probe and decode | Metadata into AssetInfo; PyAV decode with PTS timing | [#18](https://github.com/jahnavi-yelamanchi/tapesift/pull/18), [#19](https://github.com/jahnavi-yelamanchi/tapesift/pull/19), [#22](https://github.com/jahnavi-yelamanchi/tapesift/pull/22) |

## 3. In progress

- **E5 schema 1.0 (#28).** Spec approved on local commit `a6f4300` (not pushed). Builder running per the lead's log.
- **E7 runner phase 1 (#30).** Spec approved on local commit `abfad05` (not pushed). Builder running per the lead's log.
- **Spec being written:** [40-web-ui](specs/40-web-ui.md). Not on main yet.

## 4. Next

Order after the in-progress work (dates are targets from the v0.1 plan, unless noted):

1. **E3 audio (#26).** VAD, faster-whisper word timestamps, phantom-phrase filter.
2. **E4 captions (#27).** VLM captions, `tapesift[vision]` extra (Q1).
3. **E6 search (#29).** LanceDB store, text embeddings, `tapesift search`.
4. **Web UI (`tapesift serve`, spec 40).** Moved from v0.3 into v0.1 by the owner, 2026-10-20.
5. **E7 phase 2 (#30).** Runner features after the first working index.
6. **X1 talk check (#33)** on Modal, then **E9 (#32)** README and demo GIF; **E8 (#31)** packaging.

Later (not v0.1): robotics datasets, e.g. Open X-Embodiment, as a future use case. No spec yet.

Release path (unchanged, Q9): feature freeze Wed Oct 28 (v0.1 plan date); public flip on or before Oct 31; `v0.1.0rc1` to TestPyPI, then `v0.1.0` to PyPI.

Exit criteria: spec 333 as amended by Q7 (laptop-class CPU check), and the WER bound of 0.20 on `speech.mp4` (Q8).

## 5. How we work now

- **Lean mode** ([ADR 0014](adr/drafts/0014-lean-mode-ui-robotics.md)). One `feature-builder` per approved spec, each in its own worktree. One `reviewer` pass per PR. No spec-critic, council or test-auditor by default. Test sets: acceptance plus dangerous cases, about 15 to 35 per spec.
- **Models.** Opus only for decisions (`planner`, the lead). Sonnet for every other coding, test and review subagent. Haiku for `scribe`. Pass `model` explicitly.
- **Decisions.** The lead writes decision cards itself. The owner gets only spend above about $5, credentials and security.
- **Still stale until edited:** `docs/workflow.md` describes the full process. The lean block is in `CLAUDE.md` (commit `74031b4`).
- Publish rule: nothing is posted or pushed to `main` without the owner. Draft PRs only. Postable tweets sit in devlog drafts.

## 6. Decisions

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
| ADR 0009 | Claude Code subagents only; Codex dropped. Full fan-out amended 2026-10-17; lean mode from 2026-10-20 | owner | [0009](adr/0009-claude-only-subagents.md) |
| ADR 0010 | English only in v1.0 | owner | [0010](adr/0010-english-only.md) |
| ADR 0011 | Python floor 3.12 (supersedes 0005) | owner | [0011](adr/0011-python-floor-3-12.md) |
| ADR 0012 | Asset IDs: versioned `tsid1:` head/tail hash; full `sha256:` on request | owner after council | [0012](adr/0012-asset-id-scheme.md) |
| ADR 0013 (draft) | v0.1 decisions: Q1 to Q11, #21 cards, M1 cards 1 to 10 | owner (2026-10-19 and 2026-10-20) | [draft](adr/drafts/0013-v01-decisions.md) |
| ADR 0014 (draft) | Lean mode until the MVP demo; web UI in v0.1; general video only (robotics later) | owner, 2026-10-20 | [draft](adr/drafts/0014-lean-mode-ui-robotics.md) |
| Q1 | Captions in `tapesift[vision]`, not the base install | owner, 2026-10-19, on install size | [ADR 0013](adr/drafts/0013-v01-decisions.md) |
| Q9 | Repo public on or before Oct 31; then v0.1.0 to PyPI | owner | [ADR 0013](adr/drafts/0013-v01-decisions.md) |
| Spec 21 | Safe opener: 7 cards, all recommended options | owner, 2026-10-19 | [21-safe-opener](specs/21-safe-opener.md) |
| Spec 25 | M1: 10 cards (1 to 7 T3 via council, 8 to 10 T2) | owner, 2026-10-20 | [25-m1-interfaces](specs/25-m1-interfaces.md) |
| M1 card 7 | Guarded num2words shim; no LGPL package ships | owner after council | [ADR 0013](adr/drafts/0013-v01-decisions.md) (M1-7) |
| M0 | Shared media types, records, decode callbacks (6 rows) | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| E1 | HDR detection: probe opens the codec context and decodes no frames | owner, 2026-10-17 | [5-probe](specs/5-probe.md) |
| Repo | `main` takes changes only through a PR; admins included; 5 required checks | owner, 2026-10-18 | [devlog](../devlog/drafts/2026-10-18.md) |

Scorecard for the council calls: [decisions-scorecard.md](decisions-scorecard.md). "My pick" is blank for the owner (#16).

## 7. Lessons

- Parallel planners on interdependent specs diverged. Fix: write the interface spec first (retro rule; M1 was the first use).
- Council rebuttals changed a seat on the M0 `duration_s` data-loss bug, on the `tsid1` prefix (ADR 0012), and on the M1 licensing card (card 7).
- A builder's test passed on old code in an earlier PR. A mutation run caught it. In #34 the test-auditor ran 19 injected bugs: 16 caught.
- A plan rule was not applied as written for Q1. The owner chose option B on install size; the ADR says so.
- The full process burned usage with the product still unable to search a video. That is why lean mode started (ADR 0014).

## 8. Waiting on the owner

- **Talk URL and 5 queries** for X1 (Q6, CC BY talk with slides). Needed by about Oct 28. Owner writes `evals/v0.1-talk.toml`.
- **Review ADR 0014** and move it from `docs/adr/drafts/` to `docs/adr/` when accepted.
- **Public flip** on or before Oct 31 (Q9). Then the PyPI pending publishers and a protected `pypi` environment for E8. A PyPI upload makes the source public for good.
- **Scorecard "My pick"** before reading agent picks (#16). Blank rows: ADR 0007, ADR 0011, ADR 0012, and the seven M1 council rows.
- **Retro proposals** from [the Phase 0 retro](../devlog/drafts/2026-10-18-phase-0-retro.md#proposed-changes-for-the-owner-to-approve). Still open.
- **Push the approved E5 and E7 spec commits** (`a6f4300`, `abfad05`) through PRs when the owner says so.
- **Local clean-up.** Old worktrees and branches on disk. Waiting on "ok clean worktrees".

## 9. Open follow-up issues

From `gh issue list --label follow-up` (open, 2026-10-20):

- #39 CI: Dependabot for GitHub Actions pins.
- #36 Runner: wall-clock limit per file that kills a stuck worker. A read stuck in the kernel (a dead network mount) stays unbounded until this lands. E7 area.
- #35 Decode: warning details leak the full file path. Older issue; not caused by #34.
- #16 Decisions scorecard: owner fills "My pick" before reading agent picks.
- #15 C3: CROPPED (letterbox and pillarbox detection). v0.2.
- #14 E5: AssetInfo to output schema mapper; license; rotation and duration semantics. Carried into E5 (#28).
- #13 E3: audio chunk seams (600 s AudioChunks). Carried into E3 (#26).
- #11 E7: confirm DUPLICATE with a full hash; never mix ID modes in one index. Carried into E7 (#30).
- #9 Media: deinterlace (bwdif) and HDR tone mapping at decode. v0.2.

Other open v0.1 issues: #26 to #33 (E3 to E9, X1). Issue for the web UI: not yet filed (add when spec 40 is approved).

## 10. Next session

Read this file, then `gh issue list --label follow-up`, then section 8 for what needs the owner. Check `gh pr list` for open PRs; this file may lag them.
