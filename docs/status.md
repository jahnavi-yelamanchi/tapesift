# tapesift status

As of 2026-10-29. Rewritten in place by the scribe each run. Read this first; the links hold the detail.

## 1. Where we are

- **Phase: v0.1 code-complete (2026-10-29).** All v0.1 code is on `origin/main`. Lean mode ([ADR 0014](adr/drafts/0014-lean-mode-ui-robotics.md)) stays in force until the MVP demo runs and is recorded.
- **What works on main:** `tapesift index` runs over a video (probe, decode, speech-to-text, frame captions, schema 1.0 output, resume, failed-file markers). `tapesift search` finds ranked moments. `tapesift serve` is a local web UI that plays each hit from its timestamp. `tapesift doctor` reports the environment.
- **Quality numbers:** speech WER 0.067 on `speech.mp4`, against the 0.20 bound (Q8). Captions run 1.81 s per frame on 4 vCPU. Modal spend in the lean phase so far is about $0.07 (E4 bench).
- **Test count:** 1016 tests collected on main (`uv run pytest --collect-only -q`, 2026-10-29).
- **Demo: in progress.** Live demo on Modal is running now. Results not in yet.
- **Not yet done for v0.1:** the live demo result, E9 README quickstart and demo GIF (#32), X1 talk check (#33, waiting on the owner), the public flip (Q9, by Oct 31), and the PyPI release.
- `origin/main` is at ab34bd0 (#51).

## 2. Done (v0.1, merged)

| Item | What | Link |
| --- | --- | --- |
| Phase 0 | Setup, repo rules, quickstart; closed 2026-10-18 | [#23](https://github.com/jahnavi-yelamanchi/tapesift/pull/23), [#24](https://github.com/jahnavi-yelamanchi/tapesift/pull/24) |
| #21 Safe opener | Media opens through a checked fd; 9 containers; FIFOs and devices refused | [#34](https://github.com/jahnavi-yelamanchi/tapesift/pull/34), [spec 21](specs/21-safe-opener.md) |
| M1 interfaces (#25) | Records, ASR/VAD/VLM/Embedder/Store protocols, config, fakes | [#38](https://github.com/jahnavi-yelamanchi/tapesift/pull/38), [spec 25](specs/25-m1-interfaces.md) |
| v0.1 decisions | ADR 0013 draft: Q1 to Q11, #21 cards, M1 cards 1 to 10 | [#37](https://github.com/jahnavi-yelamanchi/tapesift/pull/37), [ADR 0013 draft](adr/drafts/0013-v01-decisions.md) |
| Lean mode | ADR 0014 draft; lean block in CLAUDE.md | [#40](https://github.com/jahnavi-yelamanchi/tapesift/pull/40), [ADR 0014 draft](adr/drafts/0014-lean-mode-ui-robotics.md) |
| E5 schema 1.0 (#28) | Output schema, JSON Schema file, atomic `write_json` | [#41](https://github.com/jahnavi-yelamanchi/tapesift/pull/41), [spec 28](specs/28-schema.md) |
| E7 runner, phase 1 (#30) | Per-file worker, wall-clock and no-progress limits, resume, DUPLICATE by full hash | [#42](https://github.com/jahnavi-yelamanchi/tapesift/pull/42), [spec 30](specs/30-runner.md) |
| E8 install test (#31) | Wheel built and installed outside the checkout in CI | [#44](https://github.com/jahnavi-yelamanchi/tapesift/pull/44), [spec 31](specs/31-packaging.md) |
| E6 search (#29) | LanceDB store, bge-small-en-v1.5 (ONNX) on CPU, `tapesift search` | [#45](https://github.com/jahnavi-yelamanchi/tapesift/pull/45), [spec 29](specs/29-search.md) |
| E3 speech-to-text (#26, #13) | Silero VAD gate, faster-whisper word timestamps, phantom-phrase filter, chunk seams | [#46](https://github.com/jahnavi-yelamanchi/tapesift/pull/46), [spec 26](specs/26-audio.md) |
| U1 web UI (#43) | `tapesift serve`: search, filter, play from timestamp; 127.0.0.1 by default | [#47](https://github.com/jahnavi-yelamanchi/tapesift/pull/47), [#48](https://github.com/jahnavi-yelamanchi/tapesift/pull/48), [spec 40](specs/40-web-ui.md) |
| E4 frame captions (#27) | SmolVLM2 in-process, caption-only (one sentence per frame) | [#49](https://github.com/jahnavi-yelamanchi/tapesift/pull/49), [spec 27](specs/27-captions.md) |
| Fix: tone output | Non-speech Whisper output dropped; CPU numerics put a 440 Hz tone at the skip edge | [#50](https://github.com/jahnavi-yelamanchi/tapesift/pull/50) |
| E7 index, phase 2 (#30) | `tapesift index` CLI and pipeline; aborts after 3 abandoned workers | [#51](https://github.com/jahnavi-yelamanchi/tapesift/pull/51), [spec 30](specs/30-runner.md) |

## 3. In progress

- **Live demo on Modal.** Running now. Result not in yet. When it lands, record the result in this section and in the devlog.
- **E9 README quickstart and demo GIF (#32).** Not started on main. Waits for the demo result.
- **X1 talk check (#33).** Blocked on the owner's talk URL and 5 queries. Overdue (was due about Oct 28).

## 4. Next

1. Record the live demo result (section 3).
2. E9: README quickstart and demo GIF (#32), after the demo.
3. X1 talk check (#33), once the owner adds `evals/v0.1-talk.toml`.
4. Public flip on or before Oct 31 (Q9). Then `v0.1.0rc1` to TestPyPI and `v0.1.0` to PyPI (E8 publish path).

Exit criteria: spec 333 as amended by Q7 (laptop-class CPU check), and the WER bound of 0.20 on `speech.mp4` (Q8). WER is 0.067, inside the bound. The laptop-class CPU check is not yet recorded here; confirm it before calling v0.1 done.

## 5. How we work now

- **Lean mode** ([ADR 0014](adr/drafts/0014-lean-mode-ui-robotics.md)). One `feature-builder` per approved spec, each in its own worktree. One `reviewer` pass per PR. No spec-critic, council or test-auditor by default.
- **Models.** Opus only for decisions (`planner`, the lead). Sonnet for every other coding, test and review subagent. Haiku for `scribe`. Pass `model` explicitly.
- **Decisions.** The lead writes decision cards itself. The owner gets only spend above about $5, credentials and security.
- **Still stale until edited:** `docs/workflow.md` describes the full process. The lean block is in `CLAUDE.md`.
- **Publish rule:** nothing is posted or pushed to `main` without the owner. Draft PRs only. Postable tweets sit in devlog drafts.

## 6. Decisions

Decided by: owner, plan default, lead, or owner after council.

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
| ADR 0009 | Claude Code subagents only; Codex dropped. Lean mode from 2026-10-20 | owner | [0009](adr/0009-claude-only-subagents.md) |
| ADR 0010 | English only in v1.0 | owner | [0010](adr/0010-english-only.md) |
| ADR 0011 | Python floor 3.12 (supersedes 0005) | owner | [0011](adr/0011-python-floor-3-12.md) |
| ADR 0012 | Asset IDs: versioned `tsid1:` head/tail hash; full `sha256:` on request | owner after council | [0012](adr/0012-asset-id-scheme.md) |
| ADR 0013 (draft) | v0.1 decisions: Q1 to Q11, #21 cards, M1 cards 1 to 10 | owner (2026-10-19 and 2026-10-20) | [draft](adr/drafts/0013-v01-decisions.md) |
| ADR 0014 (draft) | Lean mode until the MVP demo; web UI in v0.1; general video only (robotics later) | owner, 2026-10-20 | [draft](adr/drafts/0014-lean-mode-ui-robotics.md) |
| Q1 | Captions in `tapesift[vision]`, not the base install | owner, 2026-10-19, on install size | [ADR 0013](adr/drafts/0013-v01-decisions.md) |
| Q8 | Speech WER bound 0.20 on `speech.mp4` (measured 0.067) | owner | [ADR 0013](adr/drafts/0013-v01-decisions.md) |
| Q9 | Repo public on or before Oct 31; then v0.1.0 to PyPI | owner | [ADR 0013](adr/drafts/0013-v01-decisions.md) |
| E4 scope | Captions are caption-only in v0.1 (one sentence per frame); `media_text` empty | lead | [#49](https://github.com/jahnavi-yelamanchi/tapesift/pull/49), [spec 27](specs/27-captions.md) |
| E7 abort rule | `tapesift index` aborts after 3 abandoned workers | lead | [#51](https://github.com/jahnavi-yelamanchi/tapesift/pull/51) |
| Spec 21 | Safe opener: 7 cards, all recommended options | owner, 2026-10-19 | [21-safe-opener](specs/21-safe-opener.md) |
| Spec 25 | M1: 10 cards (1 to 7 T3 via council, 8 to 10 T2) | owner, 2026-10-20 | [25-m1-interfaces](specs/25-m1-interfaces.md) |
| M1 card 7 | Guarded num2words shim; no LGPL package ships | owner after council | [ADR 0013](adr/drafts/0013-v01-decisions.md) (M1-7) |
| E1 | HDR detection: probe opens the codec context and decodes no frames | owner, 2026-10-17 | [5-probe](specs/5-probe.md) |
| Repo | `main` takes changes only through a PR; admins included; 5 required checks | owner, 2026-10-18 | [devlog](../devlog/drafts/2026-10-18.md) |

Scorecard for the council calls: [decisions-scorecard.md](decisions-scorecard.md). "My pick" is blank for the owner (#16).

## 7. Lessons

- Parallel planners on interdependent specs diverged. Fix: write the interface spec first (retro rule; M1 was the first use).
- Council rebuttals changed a seat on the M0 `duration_s` data-loss bug, on the `tsid1` prefix (ADR 0012), and on the M1 licensing card (card 7).
- A mutation run caught a test that passed on old code (#34: 16 of 19 injected bugs caught; 3 equivalent).
- The full process burned usage with the product still unable to search a video. That is why lean mode started (ADR 0014).
- A plan rule was not applied as written for Q1. The owner chose option B on install size; the ADR says so.
- A steady tone decoded as speech on some runners: CPU numerics put its avg_logprob on faster-whisper's skip edge (#50).

## 8. Waiting on the owner

- **X1 talk URL and 5 queries (#33).** Overdue (was due about Oct 28). Owner writes `evals/v0.1-talk.toml`.
- **Public flip on or before Oct 31 (Q9).** Then the PyPI pending publishers and a protected `pypi` environment for E8. A PyPI upload makes the source public for good.
- **PyPI name decision.** Owner to confirm the name before `v0.1.0rc1`.
- **`.claude/settings.json` release deny rules.** Owner to decide and add.
- **Changelog fragments (one file per PR).** Proposed to stop CHANGELOG merge conflicts. Not decided.
- **Review ADR 0014** and move it from `docs/adr/drafts/` to `docs/adr/` when accepted.
- **Scorecard "My pick"** before reading agent picks (#16). Blank rows: ADR 0007, ADR 0011, ADR 0012, and the seven M1 council rows.
- **Retro proposals** from [the Phase 0 retro](../devlog/drafts/2026-10-18-phase-0-retro.md#proposed-changes-for-the-owner-to-approve). Still open.
- **Local clean-up.** Old worktrees and branches on disk. Waiting on "ok clean worktrees".

## 9. Open follow-up issues

From `gh issue list --label follow-up` (open, 2026-10-29):

- #39 CI: Dependabot for GitHub Actions pins.
- #36 Runner: wall-clock limit per file that kills a stuck worker. Phase 1 (#42) added wall-clock and no-progress limits; close if it covers the stuck-read case, else keep open.
- #35 Decode: warning details leak the full file path. Older issue; not caused by #34.
- #16 Decisions scorecard: owner fills "My pick" before reading agent picks.
- #15 C3: CROPPED (letterbox and pillarbox detection). v0.2.
- #14 E5: AssetInfo to output schema mapper; license; rotation and duration semantics. Carried into E5 (#41); check and close.
- #13 E3: audio chunk seams (600 s AudioChunks). Carried into E3 (#46); check and close.
- #11 E7: confirm DUPLICATE with a full hash; never mix ID modes in one index. Carried into E7 (#42, #51); check and close.

Not in the open follow-up list: #9 (deinterlace and HDR tone mapping, v0.2). The 2026-10-20 status listed it as open; confirm its state on GitHub.

Other open v0.1 issues: #32 (E9), #33 (X1). Web UI follow-ups: none filed yet.

## 10. Next session

Read this file, then `gh issue list --label follow-up`, then section 8 for what needs the owner. Check `gh pr list` for open PRs; this file may lag them.
