# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- `tapesift --version` and the package skeleton (`uvx --from . tapesift --version`).
- 25 synthetic fixtures covering every warning code in the spec, built by `make fixtures` (2.8 MB).
- `tapesift doctor [--json]`: reports Python, FFmpeg, CUDA, GPUs, NVDEC and free disk, picks the `cpu`, `gpu` or `server` profile, lists every network call tapesift can make. Exits 3 on an environment problem.
- Shared media types, the `UNREADABLE` warning code and the `Decoder` protocol; numpy and PyAV become dependencies.
- `probe` reads media metadata into `AssetInfo` with warning codes; asset IDs are `tsid1:` (size, first and last 8 MiB) or, opt-in, `sha256:` of the whole file.
- Shared v0.1 interfaces: result records, the ASR, VAD, VLM, Embedder and Store protocols, config.py with pinned models, shared test fakes; faster-whisper, LanceDB, pydantic and onnxruntime become dependencies, and captions need the new "tapesift[vision]" extra (#25).
- CPU decode with PyAV: PTS-timed, upright, downscaled frames and 16 kHz mono audio chunks (#6).
- Smoke test that runs `probe` then `PyAVDecoder` over every fixture and checks decode honors probe's rotation, duration, default audio track and warning codes (#12).
- Schema 1.0 output: `tapesift.schema.output.to_json` and atomic `write_json`, with the JSON Schema `asset-1.0.schema.json` (draft 2020-12) shipped in the package; every fixture's output validates (#28).
- CI: an install test builds the wheel, installs it with uv outside the checkout and runs version, doctor and (on demand) index plus search (#31).
- Runner v0 for `tapesift index` (phase 1, no CLI yet): per-file worker with wall-clock and no-progress limits, resume by asset ID, DUPLICATE confirmed by full hash, failed-file markers with a retry cap, signal-safe partial summary (#30, #11, #36).
- `tapesift search` and `tapesift.store.lance.search_index`: ranked speech and caption moments from a LanceDB index in `out_dir/store/`, embedded on CPU with bge-small-en-v1.5 (ONNX); on-screen words are searchable through caption text (#27) and every hit is tagged `untrusted_media` (#29).
- Audio stage: Silero VAD gate with LOW_SPEECH, faster-whisper word timestamps, a phantom-phrase filter and silence-aligned chunk seams; a Linux "models" workflow runs the real models (#26, #13).
- `tapesift serve`: a local web page to search the index, filter by file and by speech or visual, and play each hit from its timestamp. It binds 127.0.0.1 by default, serves only indexed files, and treats indexed text as untrusted. Needs `tapesift[serve]` (FastAPI, uvicorn).
- Frame captions with the pinned SmolVLM2 in-process (vision extra): prompt caption_v1, batched; on-screen words land in the caption text (#27).
- `tapesift index`: per-file worker with wall-clock and no-progress limits, resume by asset ID, DUPLICATE confirmed by full hash, failed-file markers with a retry cap, progress bar, end-of-run summary and `--json`; flags `--config`, `--profile`, `--out`, `--max-media-hours`, `--dry-run`, `--full-hash`; the run aborts after 3 workers that survive SIGKILL (#30, #11, #36).

### Fixed
- faster-whisper backend drops segments Whisper itself marks as non-speech (no_speech_prob above 0.6 and avg_logprob below -0.5), so a steady tone no longer decodes to "Beep" on some CI runners.

### Changed
- Plan: v0.1 adds a web UI (`tapesift serve` moves up from v0.3); the MVP is general video only; the build runs in lean mode until the MVP demo (ADR 0014, draft).
- **Security:** media opens through one shared opener: regular files only, read through a checked file descriptor, nine container formats (mov/mp4, matroska/webm, avi, mpegts, wav, mp3, aac, flac, ogg); playlists, concat lists, image sequences, subtitles and other formats are UNREADABLE (#21).
- Phase 0 closed: ADR 0004 amended (repo private until launch), setup guide and Phase 0 checklist updated (#23).
- `main` accepts changes only through a PR with green CI, admins included (owner, 2026-10-18).
- Subagents are Claude Code only; Codex is dropped, and each step fans out to several subagents (ADR 0009).
- Coding and review subagents (`feature-builder`, `test-writer`, `fixture-maker`, `reviewer`, `test-auditor`, `spec-critic`) run on sonnet; opus is for decisions (#20, ADR 0009 amended).
- **Breaking:** English only in v1.0. `MIXED_LANG`, its fixture and the code-switched evals are removed; non-English audio is transcribed best effort and never evaluated (ADR 0010).
- **Breaking:** Python 3.12 or newer is required; 3.11 is no longer supported (ADR 0011).
- Docs: v0.1 owner decisions drafted as ADR 0013 (Q1 to Q11, #21 cards, M1 cards 1 to 10). Captions go in `tapesift[vision]`, decided by measurement.
- Docs: M1 interface spec (#25) approved 2026-10-20; the 7 T3 cards went through a two-model council.
