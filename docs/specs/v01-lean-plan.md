# v0.1 lean plan: build order to the MVP demo

As of 2026-10-20. Lean mode (owner): get to an MVP demo fast; opus decides, sonnet builds. Scope is general video and audio files only (owner, 2026-10-20).

## Build order
Each step gives the specs, what it waits on, and what can run at the same time.

1. **Now, building:** E5 schema (#28) and E7 runner phase 1 (#30, inside one draft PR).
2. **Next, in parallel** (separate paths, one builder each):
   - **E3 audio** (#26).
   - **E4 captions** (#27). Card 1 blocks its build. Its card 6 Modal CPU run needs the owner (costed in that spec).
   - **E6 search** (#29). Being finalized, then needs approval. U1 and E7 phase 2 both depend on its card 6 (`StoreError`).
   - **E8 packaging** (#31). It touches only workflows, so it can run any time.
3. **After E3, E4 and E6 merge:** E7 phase 2 (`pipeline/`, `tapesift index`). The E7 PR leaves draft here.
4. **U1 web UI** (#40) starts as soon as E6 merges, in parallel with E7 phase 2. It builds its store from M1 constructors and tests with fakes. Its PR leaves draft after E7 merges, because it imports `scan_assets`. Then comes its one Modal browser check (40 card 6).
5. **After E7 and U1 merge:**
   - **X1** talk check (#33, needs the owner's talk URL and 5 queries);
   - **E9** README and demo GIF (#32), which now records the UI, not only the terminal.
6. **Release** as planned: freeze Oct 28, public flip by Oct 31, then v0.1.0. If U1 misses the freeze, it ships as v0.1.1. The CLI demo doesn't wait for it.

Critical path: E6 approval, then E6, then U1 and E7 phase 2 together, then the demo. E3 and E4 have to land before E7 phase 2 too.

## Demo done (plain English)
Someone takes a recorded 10-minute talk and runs two commands. The first indexes it on a laptop-sized computer. The second, `tapesift serve`, opens a page in their web browser. They type a question in everyday words, like "where do they talk about pricing". In a second or two they get a short list of moments: each one shows the time, a small picture from the video and the words spoken or shown there. Clicking a moment plays the video from exactly that spot. They can narrow results to one file, or to speech versus what is on screen. Any text that came from the video itself, such as words on a slide, is labelled as untrusted and shown as plain text, never run. All of this happens on the user's own machine, with nothing uploaded. Because the owner's laptop doesn't load AI models (ADR 0008), the demo run happens on a laptop-sized Modal machine through `scripts/cloud/modal_ui.py`, about $0.50 a session (owner OK needed).

## Later: robotics datasets (for example, Open X-Embodiment, LeRobot mp4 plus parquet)
- OXE is on the HF Hub in LeRobot format: AV1 mp4 plus JSONL or parquet metadata, so there's no TensorFlow or RLDS reader. `IPEC-COMMUNITY/*_lerobot` (31 datasets, v2.x) has one mp4 per episode plus `meta/episodes.jsonl` with `tasks`. `lerobot/*` (v3.0) packs many episodes into each mp4, with `from_timestamp`/`to_timestamp` in parquet.
- tapesift already indexes these videos: PyAV decodes AV1 (`libdav1d`), and times come from PTS. Still missing: a searchable per-episode `task` row (an M1 Store and record change), and episode or derived-step labels in the UI.
- Size (summed from info.json, 2026-10-20): about 1,670 one-camera hours and 960k episodes. Captioning it at 1 fps on Modal L4 is about $100-300; a 600-episode demo is under $2. Both need the owner's OK.
