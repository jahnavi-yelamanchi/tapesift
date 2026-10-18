# tapesift status

As of 2026-10-18. Rewritten in place by the scribe each run. Read this first; the links hold the detail.

## 1. Where we are

Two meanings of "Phase 0": "Phase 0: setup" in the [spec](spec.md) (P0.1 to P0.7) is closed. The engine phase in [ADR 0001](adr/0001-three-phase-build.md) (Oct 14 to Dec 6) is under way.

- Phase 0 setup closed. Fresh-clone check passed 2026-10-18 (419 tests then, about 30 s). Main now has 451 tests after #22.
- `make check` on main at a922886: 451 passed, 2 GPU tests deselected (run 2026-10-18).
- Engine milestone merged: M0 shared media types (#10), E1 probe (#18), E2 CPU decode (#19). Specs: [5-probe](specs/5-probe.md), [6-decode](specs/6-decode.md).
- #12 probe-then-decode integration test merged in #22 (a922886). Issue #12 closed. Mutation check: 6 of 7 injected decode bugs caught; the survivor got a test.
- #23 docs close-out merged (0be4a3f): ADR 0004 amendment, setup guide, Phase 0 boxes ticked.
- #20 merged: sonnet for coding and review subagents, opus for decisions.
- Branch protection on `main`: PR required, admins included, 5 required checks (owner, 2026-10-18).
- L4 doctor re-run on Modal 2026-10-18 (`docs/verification/doctor-L4.json`). Open: its `disk_free_gib` is in bytes; the code emits GiB.
- Phase 0 retro and the 2026-10-18 devlog are in the draft PR `docs: Phase 0 retro and 2026-10-18 devlog` (draft, on branch `docs/phase0-retro`). Files: [retro](../devlog/drafts/2026-10-18-phase-0-retro.md), [devlog](../devlog/drafts/2026-10-18.md).
- E1 paused once on a decision card: HDR detection under PyAV 19. The owner answered: probe opens the codec context without decoding frames.
- Repo stays private until launch (ADR 0004, amended).

## 2. What is running

Nothing. No builders, no background sessions. The retro PR is a draft and waits for review.

## 3. How we work

Claude Code subagents only, several per step ([ADR 0009](adr/0009-claude-only-subagents.md)). Planner and spec-critic write and attack each spec. Parallel feature-builders each work in their own worktree. Reviewer and test-auditor run on every PR. Two-model council (one opus, one sonnet, then a rebuttal round) decides one-way doors. Scribe handles bookkeeping. The owner gates spec approval, decisions, merges and context edits (ADR 0009; [workflow](workflow.md)).

## 4. Decisions so far

Decided by: owner, plan default, or owner after council.

| ID | Decision | Decided by | Link |
| --- | --- | --- | --- |
| ADR 0001 | Build in three phases: engine, evals and post-training, self-training | owner | [0001](adr/0001-three-phase-build.md) |
| ADR 0002 | tapesift starts and stops vLLM itself on NVIDIA GPUs | owner (plan) | [0002](adr/0002-managed-vllm.md) |
| ADR 0003 | Add `tapesift mcp` in v0.3 | owner (plan) | [0003](adr/0003-mcp-server.md) |
| ADR 0004 | Name tapesift, Apache-2.0; private until launch (amended 2026-10-16, text written 2026-10-18) | plan defaults D1, D3, D11 | [0004](adr/0004-name-license-public.md) |
| ADR 0005 | Python floor 3.11 (superseded) | plan default | [0005](adr/0005-python-floor.md) |
| ADR 0006 | Messy-data fixtures are small synthetic files, committed | plan default D7 | [0006](adr/0006-test-fixtures.md) |
| ADR 0007 | Speech fixture synthesized with espeak-ng | owner | [0007](adr/0007-speech-fixtures-espeak.md) |
| ADR 0008 | Laptop only builds code; models, datasets and training run in the cloud | owner (replaces plan default D2) | [0008](adr/0008-laptop-builds-cloud-computes.md) |
| ADR 0009 | Claude Code subagents only, several per step; Codex dropped | owner | [0009](adr/0009-claude-only-subagents.md) |
| ADR 0010 | English only in v1.0 | owner | [0010](adr/0010-english-only.md) |
| ADR 0011 | Python floor raised to 3.12 (supersedes 0005) | owner | [0011](adr/0011-python-floor-3-12.md) |
| ADR 0012 | Asset IDs: versioned `tsid1:` head/tail hash by default, full `sha256:` on request | owner after council | [0012](adr/0012-asset-id-scheme.md) |
| Repo | `main` takes changes only through a PR; admins included; 5 required checks | owner, 2026-10-18 | [devlog](../devlog/drafts/2026-10-18.md) |
| M0 | `Frame.pixels` is `NDArray[np.uint8]` (h, w, 3) RGB, set read-only | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | Records are frozen stdlib dataclasses, not pydantic | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | `probe(path, *, full_hash=False)` is a plain function, not on the Decoder protocol | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | Audio is an `Iterator[AudioChunk]` stream; no `AudioTrack` | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | Non-fatal decode problems go to a required `warn` callback | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | `UNREADABLE` is a new code for files that cannot be opened as media | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | `duration_s` is the video stream end (audio is clipped to it); container duration as fallback | owner after council | [4-media-types](specs/4-media-types.md#decision-cards) |
| M0 | Early EOF more than 1.0 s before `duration_s` is a `PARTIAL_DECODE` gap run (R10 amendment) | owner after council | [4-media-types](specs/4-media-types.md) (R10 amendment), [6-decode](specs/6-decode.md) |
| E1 | HDR detection: probe opens the codec context and decodes no frames | owner (answer to a paused card, 2026-10-17) | [5-probe](specs/5-probe.md) |

## 5. Lessons

- Parallel planners on interdependent specs diverged. Fix: write the interface spec first (PR #7).
- Council rebuttal rounds changed the recommendation twice: a `duration_s` data-loss bug, and the `tsid1` prefix (ADR 0012).
- Review of PR #10 caught `Frame` losing its read-only flag after pickling, and view aliasing in code copied from an approved spec.
- A lead instruction about small-file IDs was wrong and was reverted.
- The PyAV wheel license was verified as LGPL-3.0+; planners had claimed GPL.
- FFmpeg 7.1 (fixtures) and PyAV 19's bundled FFmpeg 9 expose different metadata, including HDR. Pinned numbers may shift (see [5-probe](specs/5-probe.md)).
- A reviewer's suggestion on #22 was wrong per the spec: the first `start_offset` frame is about 1.52 s, not 0. The lead checked it before forwarding. Rule: check reviewer suggestions against the spec first.
- Shape-and-order checks let a broken decoder pass. Pinned spec values and a mutation run caught it.
- A builder's test passed on old code. A mutation run would have shown it; proposal (ii) in the retro makes that a standard test-auditor step.

## 6. Waiting on the owner

- Review the draft PR `docs: Phase 0 retro and 2026-10-18 devlog`, then merge it. Nothing merges without your approval.
- Approve, change or reject the four retro proposals in [the retro](../devlog/drafts/2026-10-18-phase-0-retro.md#proposed-changes-for-the-owner-to-approve). Nothing is applied until you do. The retro file sits in `devlog/drafts/` for now; move it to `docs/retros/phase-0.md` if you prefer.
- Fill "My pick" in [the decisions scorecard](decisions-scorecard.md) (issue #16) before reading agent picks. Rows still blank: ADR 0007, ADR 0011, ADR 0012.
- Set the public-flip date (ADR 0004 open question).
- Before the three draft tweets go out, fix two claims in them: the test count (451, not 419) and the fixture count (21 broken plus 4 clean controls). Details in [the devlog](../devlog/drafts/2026-10-18.md#postable).
- Decide whether to file an issue for the `disk_free_gib` unit mismatch in `docs/verification/doctor-L4.json`.

## 7. Open follow-ups

Open issues with the `follow-up` label (`gh issue list --label follow-up`):
- #11 E7: confirm DUPLICATE with a full hash; never mix ID modes in one index.
- #13 E3: handle audio chunk seams (600 s AudioChunks).
- #14 E5: AssetInfo to output schema mapper; license; rotation and duration semantics.
- #15 C3: owns CROPPED (letterbox and pillarbox detection on sampled frames).
- #16 Decisions scorecard: owner fills "My pick" before reading agent picks.
- #21 Media: demuxer allow-list and one shared safe opener for every stage.

Other open issues:
- #9 Media: deinterlace (bwdif) and HDR tone mapping at decode (brief).

Not yet filed:
- `disk_free_gib` is in bytes in `docs/verification/doctor-L4.json`; the code emits GiB.
- Rotation-direction mutation was not run for #22 (permission check). Covered by the rot90 pixel test only.

Closed: #12 (merged in #22).

## 8. Next

1. v0.1 starts with #21 (demuxer allow-list and shared safe opener), before the runner.
2. Then the follow-ups E3 (#13), E5 (#14), E7 (#11) and C3 (#15).
3. v0.1 backlog from [docs/spec.md](spec.md): E3 audio (16 kHz, VAD, faster-whisper, phantom-phrase filter); E4 VLM captions; E5 schema 1.0 JSON with validation; E6 LanceDB store and search; E7 runner v0 with per-file isolation and resume; E8 packaging and PyPI release; E9 README quickstart and demo GIF.
