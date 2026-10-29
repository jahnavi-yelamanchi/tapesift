# 2026-10-29: v0.1 code-complete (draft)

All v0.1 code is on `origin/main`. What is left is the live demo, the README and GIF, the talk check, and the public flip.

## What happened

- **Lean phase, 2026-10-20 to 10-29.** Thirteen PRs merged (#37, #38, #40, #41, #42, #44 to #51). Lean mode ([ADR 0014](../../docs/adr/drafts/0014-lean-mode-ui-robotics.md)) cut each feature to one builder and one reviewer.
- **Speech (#46, #50).** faster-whisper word timestamps behind a Silero VAD gate. Speech WER 0.067 on `speech.mp4`, against the 0.20 bound (Q8). Then a fix (#50): a steady 440 Hz tone decoded as speech on CPU, because its avg_logprob sat at -0.99, on faster-whisper's -1.0 skip edge. Non-speech output is now dropped.
- **Captions (#49).** SmolVLM2 in-process, one sentence per frame, on-screen words included. `media_text` stays empty in v0.1. 1.81 s per frame on 4 vCPU.
- **Search and UI (#45, #47, #48).** LanceDB store, CPU embeddings, `tapesift search`. Then `tapesift serve`, a local page that plays each hit from its timestamp. It binds 127.0.0.1 and treats indexed text as untrusted.
- **Index (#41, #42, #51).** Schema 1.0 output with a JSON Schema file. The runner gets resume, DUPLICATE checks and failed-file markers. `tapesift index` (#51) is the CLI on top; the run aborts after 3 abandoned workers (lead decision).
- **Install (#44).** CI builds the wheel, installs it outside the checkout, and runs version, doctor and, on demand, index plus search.
- **Numbers.** 1016 tests collected on main. Modal spend in the lean phase is about $0.07 (E4 bench).

## Still open

- **Demo: in progress.** Live demo on Modal is running. Result not in yet.
- **E9 (#32).** README quickstart and demo GIF. After the demo.
- **X1 (#33).** Talk check. Needs the owner's talk URL and 5 queries. Overdue (was about Oct 28).
- **Public flip.** On or before Oct 31 (Q9). Then PyPI.
- **Owner calls.** PyPI name. `.claude/settings.json` release deny rules. Changelog fragments (one file per PR, proposed, not decided).

## Postable

Draft tweet. Post only after the owner signs off. No links; the repo is private.

"tapesift v0.1 code is on main: index a video, search what was said and what was on screen, and jump to the exact moment. Speech word error rate 0.067 on our test clip. Talk check and demo still to come."
