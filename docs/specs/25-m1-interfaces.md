# 25. M1: v0.1 shared interfaces (records, backend and store Protocols, config, fakes, dependencies)

Issue: #25   Lane: Core (interface spec; card 9's lane edit is in this PR)   Status: approved 2026-10-20 (owner, gate 1)
Revisions: 2026-10-19 r2, for the owner's Q1 answer and spec-critic findings 1-14. Variant A is gone. A CPU torch source applies to dev and CI. Captions-off is now visible. Times are clamped at the stage boundary. A failed-asset marker caps retries at 2. A VAD Protocol is added. Embedder calls take `kind`. `Hit.media_text` is a separate field. Backend ids are forward-compatible. `Store.delete` is added. A shared `fetch_pin` handles model fetches. Cards 7 (now T3) and 10 (new) changed.
2026-10-20 r3: the owner decided every card after the two-model council and rebuttal. Changes:
- `vlm.max_batch` is `None` by default, resolved per profile.
- A path key written in a config file resolves against that file's folder.
- num2words is replaced by a guarded shim, and transformers is pinned exactly.
- `unpinned` is an exact literal.
- The AGENTS.md lane edit is in this PR's scope.
- The E3 tracemalloc test is required.
Dependents, all planned against this approved spec: E3 #26, E4 #27, E5 #28, E6 #29, E7 #30, E8 #31, E9 #32, X1 #33.

## Decision cards

All ten cards were decided by the owner on 2026-10-20. T3 cards 1-7 went through the two-model council and a rebuttal round; the owner decided T2 cards 8-10 directly. Each card ends with the decision; the rest of this spec follows it.

The planner checked every external fact on 2026-10-19, against the PyPI JSON API, the HF model API (metadata only), upstream source at the pinned tags, the PyTorch CPU index, and `uv lock` / `uv pip compile` runs that resolved metadata only.

### Decision (T3): card 1. Unexpected per-file exceptions, retries, and where v0.1 reports them
**Context.** A model crash, OOM or backend exception on one file isn't a `StageError`. No warning code fits it: `UNREADABLE` and `PARTIAL_DECODE` have fixed meanings (M0 cards), and a new code would need a fixture that no media file can provide. The spec rule allows "a warning code on the asset **or a line in `tapesift report`**", but `report` arrives in v0.3. A deterministic failure must not be retried on every run.

**Options.**
- **A. A new code, `STAGE_FAILED`.** The record is written with whatever succeeded. Cons: a schema bump, a new spec row, an edit to the fixture-coverage test, and a transient OOM is never retried.
- **B. Reuse `UNREADABLE` or `PARTIAL_DECODE`.** Cons: it blurs meanings that M0 fixed.
- **C. The asset fails, with a marker and a retry cap** (assumed below, R5):
  - No JSON and no store rows are written.
  - E7 writes `out_dir/failed/<asset_id>.json` atomically: `{"path", "stage", "exception": "<Type>", "error": "<Type>: <message>", "attempts", "tapesift"}`.
  - A rerun retries the asset only while `attempts < 2` **or** the marker's `tapesift` version differs from the running one. Otherwise the asset is skipped with the line `failed before (2 attempts on <version>); not retried`.
  - A success deletes the marker.
  - v0.1 shows every failure in the end-of-run summary (stderr, and the `index --json` output). The markers are what `tapesift report` (v0.3) reads.
  - `StageError`s still degrade instead of failing: that stage contributes nothing, its warning goes on the record, and the record is written.

  Pros: no schema change; transient failures retry once; an upgrade retries again. Cons: the other stage's output for that file is dropped.

**Hardest to reverse.** A (an enum value users filter on).
**Recommendation.** C.
**Would change my mind.** Real runs show one stage crashing deterministically and dropping transcripts users want. Then A, at a schema minor bump.
**Decided 2026-10-20 (owner, after council and rebuttal):** C. The marker records the stage and the exception type. The cap is 2 attempts per tapesift version.

### Decision (T3): card 2. Nullable caption fields in schema 1.0: `shot` and `conf`
**Context.** Shot detection is C3 (v0.2), and `strategy = "fixed"` stays a mode after C3, so fixed sampling never has shots. A caption's confidence needs token log-probabilities. SmolVLM through transformers can give them, but OpenAI-compatible endpoints (C6) may not.

**Options.**
- **A.** (assumed below) In v0.1, `"shots": []` and every caption has `"shot": null`. Captions may have `"conf": null` when the backend can't compute one. E5's JSON Schema types both as `<type> | null` from 1.0. Pros: true in every mode and backend. Cons: consumers handle null.
- **B.** One synthetic whole-asset shot, and `conf` is required (a backend must invent one). Cons: false boundaries; made-up confidence.
- **C.** Leave out `shots`, `shot` and `conf` in v0.1. Cons: not the 1.0 shape the spec promises.

**Hardest to reverse.** B (consumers trust fake values).
**Recommendation.** A. `utterances[].conf` stays required, because Whisper always gives log-probabilities.
**Would change my mind.** C3 decides `fixed` should emit time-window shots.
**Decided 2026-10-20 (owner, after council and rebuttal):** A.

### Decision (T3): card 3. `Hit`, the `tapesift search --json` shape
**Context.** `--json` is public. Spec 513 (Y1) asks for media words with "clear delimiters" and `"trust": "untrusted_media"`. Spec 218 says "confidence", but v0.1's score is uncalibrated cosine similarity.

**Options.**
- **A.** (assumed below) The output is `{"query": "<q>", "hits": [...]}`. Each hit is `asdict(Hit)` with exactly these keys:
  - `asset_id` and `path`;
  - `start_s` and `end_s` (a visual hit is a point: both equal the caption's `t_s`);
  - `modality`: `"speech"` or `"visual"`, and the CLI's `any` maps to None;
  - `text`: the utterance text or the caption text;
  - `media_text`: the on-screen words, a separate list (`[]` for speech);
  - `score`: higher is better within one query, and not comparable across queries;
  - `trust`: always `"untrusted_media"`.

  Spec 218 is reworded from "confidence" to "relevance score". Pros: the media text is delimited by structure, not by string conventions; the output is safe by default. Cons: a constant field.
- **B.** As in A, but `media_text` is joined into `text`, and `trust` is added in S8. Cons: injection text is mixed into the caption; v0.1 consumers get untagged results.
- **C.** A bare JSON array. Cons: the top level can never grow.

**Hardest to reverse.** C; then any field that ships.
**Recommendation.** A.
**Would change my mind.** Y1 needs untagged v0.1 output as a baseline. Its harness can strip the tag instead.
**Decided 2026-10-20 (owner, after council and rebuttal):** A. `score` is documented as not comparable across queries. Consumers must tolerate new `modality` values (S3 adds more), and the `Modality` and `Hit` docstrings say so.

### Decision (T3): card 4. The v0.1 config keys, defaults and `--config`
**Context.**
- Spec 229-262 lists the v1.0 keys. `strategy = "shots+dedupe"` (the default) needs C3; `shot_threshold`, `dedupe_hamming` and `max_frames_per_shot` also need C3; `vlm.endpoint` needs C6; `[safety]` needs Y1-Y3.
- `asr.audio_track` (spec 296) is missing from the block.
- `vlm.max_batch = 32` was sized for a GPU server. v0.1 runs the VLM in-process on CPU, where memory grows with the batch and throughput gains flatten after a few frames.
- With only `./tapesift.toml`, a script running from another directory can't point at its config.

**Options.**
- **A.** (assumed below; table in Interfaces)
  - v0.1 accepts exactly the keys it honours. Every other spec key is an unknown-key error until its item adds it, which is an additive change.
  - `sampling.strategy` accepts only `"fixed"`.
  - `asr.audio_track` is added.
  - `vlm.backend` gains `"none"`.
  - Model names are pinned names only.
  - **`vlm.max_batch` defaults to 8.** C6 raises it for GPU serving.
  - `out_dir` is relative to the current directory; one index per `out_dir`; `index` and `search` read the same one.
  - (Both of these were changed by the decision below.)
  - **`index` and `search` take `--config FILE`.** Without it, `./tapesift.toml` is used if present.
  - Precedence: flag > file > default.
  - `profile` picks the device: CUDA only for `gpu` or `server`. When it is unset, E7 fills it from doctor's `pick_profile`.

  Pros: no silent no-op keys; CPU-safe defaults. Cons: the spec's full v1.0 example file doesn't load in v0.1.
- **B.** Accept every spec key, and warn on the ones that aren't implemented. Cons: silently ignored settings, and a false default.
- **C.** Accept every key, and error on a non-default value for an unimplemented one. Cons: freezes later keys' types now.

**Hardest to reverse.** B or C (they publish types early). `--config` is a CLI flag: once shipped, it can't be removed.
**Recommendation.** A.
**Would change my mind.** E4 measures that `max_batch` 8 is much slower than 16 or 32 on the CI runner without a memory problem. Then raise the default by card.
**Decided 2026-10-20 (owner, after council and rebuttal):** A, with two changes:
1. **`vlm.max_batch: int | None = None`**, resolved per profile by `config.vlm_max_batch(cfg)` from `VLM_MAX_BATCH`. In v0.1 that is 8 for every profile, with an unset profile treated as `cpu`. C6 raises the gpu and server values.
2. **A path key written in a config file** (`out_dir` now; future path keys too) resolves against that config file's folder. `--out` and the default stay relative to the current directory. A test keeps every `Path` field listed in `_PATH_KEYS`.

### Decision (T3): card 5. `"eng"` vs `"en"`
**Context.** The M0 card (owner, after council) fixed `asset.audio.lang` as the container tag as written: ISO 639-2, `"eng"`, in the fixtures. Spec line 271 shows `"en"`. Whisper reports ISO 639-1 (`"en"`).

**Options.**
- **A. Two documented meanings** (assumed below). `asset.audio.lang` is what the container claims, as written (`"eng"`, `"und"` or free text). `utterances[].lang` is what the ASR detected, in ISO 639-1. Fix spec 271 to `"eng"`; E5 documents both in the JSON Schema. Pros: lossless; matches M0. Cons: two formats in one file.
- **B. Map container tags to 639-1.** Cons: a table of about 180 entries or a new dependency, and `"und"` and free text have no mapping.
- **C. Map ASR output to 639-2.** Cons: a table too, and the native code is lost.

**Hardest to reverse.** B or C.
**Recommendation.** A.
**Would change my mind.** A consumer has to join the two. Then add a separate normalized field (a minor bump).
**Decided 2026-10-20 (owner, after council and rebuttal):** A. E5's JSON Schema `description`s state both meanings, and say that `und` (or any other container tag) is passed through as written.

### Decision (T3): card 6. Backend ids in `provenance`
**Context.** Spec 277 shows `"faster-whisper:large-v3-turbo@<rev>"`. v0.2's endpoint backends (C6: vLLM or a user's OpenAI-compatible server) have model ids with case and `/` (`Qwen/Qwen2-VL-2B-Instruct`), and often no revision.

**Options.**
- **A.** (assumed below) `"<backend>:<model>@<revision>"`, validated by `BACKEND_ID_RE = [a-z0-9-]+:[^\s@]+@(?:[0-9a-f]{40}|unpinned)`:
  - the backend is lowercase;
  - the model is any token without whitespace or `@`, with case and `/` allowed;
  - the revision is the full 40-hex commit SHA for every pinned HF model (a config test enforces it), or the literal `unpinned` when the server can't say;
  - null when that stage didn't run, and `vlm` and `prompt` are null together.

  Pros: one string form now and in v0.2; greppable. Cons: `unpinned` ids can't reproduce a run.
- **B.** A 12-hex short SHA. Cons: ambiguous, and doesn't match the pins.
- **C.** A structured object `{backend, model, revision}`. Cons: a shape change from spec 277.

**Hardest to reverse.** C.
**Recommendation.** A.
**Would change my mind.** C6 finds that servers report a revision we must record separately.
**Decided 2026-10-20 (owner, after council and rebuttal):** A. The revision is either 40 lowercase hex or exactly the literal `unpinned`, and `BACKEND_ID_RE` enforces that.

### Decision (T3, licensing): card 7. Dependencies beyond the owner's Q2 list, including an LGPL package
**Context.** Reading upstream source at the pinned versions turned up three packages that the owner's Q2 A list doesn't name:
- **huggingface-hub.** It's already installed through faster-whisper. `tapesift.hub.fetch_pin` imports it directly, so it should be declared.
- **num2words 0.5.14, LGPL-2.1** (its COPYING file, checked 2026-10-19). transformers 5.20.2's `SmolVLMProcessor.__init__` raises `ImportError` without it (`processing_smolvlm.py` 136-139). It brings `docopt` 0.6.2 (MIT), which is sdist-only and built at install.
- **An image backend.** torchvision is the default when installed; pillow (MIT-CMU) is used automatically when torchvision is absent (`image_processing_auto.py` `_resolve_backend`).

Only the image backend goes in the `vision` extra (Q1 B); num2words is avoided (see the decision).

**Options.**
- **A.** (not chosen; the fallback under Risks) Declare `huggingface-hub` in the base. Add `num2words` and `pillow` to `vision`. Pros: pillow is small and not coupled to the torch version; an LGPL library that is imported unmodified, and installed by the user, is compatible with Apache-2.0 distribution. Cons: an LGPL package in the dependency tree, plus a source build of docopt at install.
- **B.** As A, with torchvision (BSD) instead of pillow. Cons: it must match torch's version exactly; bigger.
- **C.** No num2words: E4 subclasses the processor to skip the check. Cons: private-API coupling that breaks on transformers upgrades.

**Hardest to reverse.** Any licence that ships in a release. A is removable later if C6 replaces the in-process VLM.
**Recommendation.** A.
**Would change my mind.** A licence review rejects LGPL dependencies (then C), or E8's install measurement shows docopt's build is slow.
**Decided 2026-10-20 (owner, after council and rebuttal):** a guarded shim, not A:
- `huggingface-hub` goes in the base, and `pillow` in `vision`. **No num2words.**
- transformers is pinned exactly: `transformers==5.20.2`.
- E4's loader (the only code that builds the SmolVLM processor; M1 builds none) checks `hasattr(transformers.models.smolvlm.processing_smolvlm, "num2words")` and raises `ModelLoadError` if the attribute is absent.
- Only then does it set that module global, when it is None, to a stub. The stub raises `RuntimeError("num2words stub: video prompts are not used in tapesift v0.1")` if called. The video path is never used in v0.1.
- The fallback (option A, adding num2words, LGPL-2.1) is under Risks.

### Decision (T2): card 8. The `Embedder` Protocol: text only, `kind`, and truncation
**Context.** Spec 123 has `embed_images` (S3, v0.3). bge-small-en-v1.5 embeds queries with an instruction prefix ("Represent this sentence for searching relevant passages: ") and passages without one. It accepts at most 512 tokens.

**Options.**
- **A.** (assumed below) `id`, `dim`, and `embed_text(texts, *, kind: Literal["query", "passage"])`, with `kind` required. Texts over the model's limit are truncated to it, never rejected. No `embed_images` until S3. Pros: the asymmetry is explicit at every call. Cons: adding an image method later breaks third-party embedders, and there are none before 1.0.
- **B.** No `kind`; the store adds the prefix itself. Cons: model knowledge leaks into the store.
- **C.** Keep `embed_images` as a stub. Cons: a method that lies.

**Hardest to reverse.** B (stores that already prefix their text).
**Recommendation.** A.
**Would change my mind.** The pinned embedder changes to a symmetric model. `kind` then becomes a no-op, which is harmless.
**Decided 2026-10-20 (owner):** A.

### Decision (T2): card 9. Lane ownership of `schema/`, `config.py` and the interface files (an AGENTS.md edit, approved for this PR)
**Context.** The AGENTS.md lanes don't list `src/tapesift/schema/` or `src/tapesift/config.py` (spec 137-138). `warning_codes.py` (from M0) is used by every lane. Context edits are the owner's gate 4. The owner approved this one for the M1 PR on 2026-10-20.

**Options.**
- **A.** (assumed below) Replace the Core line, and add one line:
  ```
  - Core: src/tapesift/{cli,pipeline,runner,store,audio,vision,serve,schema}/, src/tapesift/config.py, src/tapesift/hub.py
  - Interfaces (any lane, only through an approved interface spec such as M0 or M1): src/tapesift/warning_codes.py, src/tapesift/config.py, src/tapesift/hub.py, src/tapesift/*/types.py, src/tapesift/schema/records.py, tests/fakes.py, tests/contract/
  ```
- **B.** Add `schema/` and `config.py` to Core only. Cons: shared files stay editable by any Core builder.
- **C.** No edit; each spec grants its paths.

**Hardest to reverse.** None of the three.
**Recommendation.** A.
**Would change my mind.** The owner prefers per-spec grants.
**Decided 2026-10-20 (owner):** A. This PR makes the edit exactly as written above.

### Decision (T2): card 10. The v0.1 platform floor
**Context.** Spec 198 promises the cpu profile on "Any laptop, Mac included", and spec 206 says "macOS arm64". Observed 2026-10-19:
- onnxruntime 1.31.0 has macOS wheels only for `macosx_14_0_arm64`. `uv pip compile` at uv's default macOS target is unsatisfiable, and succeeds with `MACOSX_DEPLOYMENT_TARGET=14.0`.
- lancedb 0.40.0 ships `macosx_11_0_arm64` and `manylinux_2_28` wheels only, with no sdist.
- torch 2.14.1 has macOS wheels only for `macosx_14_0_arm64`.

So there's no Intel Mac and no macOS 13, and Linux needs glibc 2.28+.

**Options.**
- **A.** (assumed below) Accept the floor and edit the spec. Line 198: `Any laptop, Mac included` becomes `A Linux x86_64 laptop (glibc 2.28+) or an Apple Silicon Mac on macOS 14+`. Line 206: after `macOS arm64 runs the \`cpu\` profile and is tested in CI on the smoke suite.`, insert ` Floors: glibc 2.28+ on Linux, macOS 14+ on Apple Silicon; Intel Macs are not supported (onnxruntime, lancedb and torch ship no macOS x86_64 wheels).` E8 and E9 state the same.
- **B.** Cap onnxruntime at a version with older macOS wheels. Cons: holds back a security-relevant runtime, and lancedb and torch still exclude Intel.
- **C.** Platform markers with per-OS pins. Cons: a forked lock and two runtimes to test.

**Hardest to reverse.** Promising Intel Macs (B or C). Raising a floor later breaks users who were promised it.
**Recommendation.** A.
**Would change my mind.** A buyer conversation needs Intel Macs (then Docker, S5).
**Decided 2026-10-20 (owner):** A. This PR makes the spec.md edits to lines 198 and 206.

### Decided by the owner, 2026-10-19 (recorded, not reopened)
- **Q1 B.** transformers, torch and pillow live in a `vision` extra (num2words is replaced by a shim, card 7); the base has no torch. Measured on GitHub Actions on 2026-10-19 (branch `exp/q1-install-timing`, `docs/experiments/2026-10-19-q1-install-timing.md`, run 39347647667; `uv pip install`, no cache, one run per OS):

  | OS | lean install | lean venv | with VLM install | with VLM venv |
  | --- | --- | --- | --- | --- |
  | Linux | 4 s | 778 MB | 33 s | 6.1 GB (about 4 GB is CUDA wheels) |
  | macOS | 3 s | 479 MB | 10 s | 1.1 GB |

  The time bar held either way; the owner chose B for size.
- **Q2 A (lean dependencies).** faster-whisper 1.2.1 (Silero VAD bundled, used through `faster_whisper.vad`), lancedb 0.40, pydantic 2.14 direct, tokenizers and onnxruntime direct for the ONNX embedder, jsonschema in the dev group. **M1 is the only PR that edits `pyproject.toml` and `uv.lock`.**
- **Q3 A.** Upstream models pinned by full 40-character commit SHA. The weight rule becomes "safetensors, CTranslate2 or ONNX; never pickle; `trust_remote_code` off".
- **Q4 A.** A `model` pytest marker, deselected in `make check`. E3 adds the Linux-only `models` CI job: advisory until it has been green 3 times, then required.
- **Q5 A.** Laptop tests may run the Silero VAD bundled in faster-whisper. It is package data, so it carries no `model` marker.
- **Q8 A.** WER ≤ 0.20 after the normalizer in `src/tapesift/eval/wer.py` (E3).
- **Q9 A.** The repo goes public on or before Oct 31; v0.1.0 goes to PyPI (E8).
- **Q10 B.** `--max-hours` and `--dry-run` ship (no cost line); `--workers` moves to S1/v0.3 (E7 edits spec 217).

### Push-back on finding 7, accepted by the owner (2026-10-20)
**Finding 7: make `ASR.transcribe` take a streaming `Iterable[AudioChunk]`.** This spec keeps `Sequence[AudioChunk]` and makes streaming the stage's rule instead (R8).
- Memory is bounded by the stage, not by the parameter type. `transcribe_asset` passes the backend one chunk at a time (plus the seam overlap), and a 600 s chunk is 9.6 M float32 samples, or 38.4 MB.
- A generator parameter would make every backend handle lazy-input lifecycles (partial consumption, exceptions mid-iteration). It would also stop C5 (spec 354, batched ASR across files) from passing chunks from several files in one call.
- Spec 116 and M0's audio card already fix `Sequence`.

**E3's tracemalloc memory test is a required E3 acceptance item** (R8, "E3 must" below).

## Goal
E3, E4, E5, E6 and E7 can be specced and built in parallel against one merged source of truth, the same role M0 (#4) played for E1 and E2. After this PR, main has:
- the result records and `Hit`, plus the time-clamp helper;
- the `ASR`, `VAD`, `VLM`, `Embedder` and `Store` Protocols;
- the stage entry-point signatures;
- `config.py` with the v0.1 keys and model pins;
- `hub.fetch_pin`;
- one set of fakes, with contract tests that real backends join later;
- doctor's `vision` line;
- every v0.1 dependency, with CPU torch for Linux dev and CI;
- the `model` marker.

## Read first
- docs/spec.md:
  - Architecture, Interfaces (106-128); repo layout (130-158);
  - Install (180-208; especially 184, 190, 198, 204, 206);
  - CLI, config and output schema (210-281);
  - Messy multimodal data (287, and the AV-length, no-audio, low-speech and burned-in-text rows);
  - Y1 (513), Y3 (524-525), Y5 (537);
  - Engineering standards (730-745); C5 (354); D4 and D5 (813-814).
- docs/specs/4-media-types.md, in full: R1, R3, R7, R8, R10, the audio-stream card (seams), and the emitter table.
- docs/specs/21-safe-opener.md (approved). Its paths don't overlap with this PR; only CHANGELOG can conflict.
- ADRs 0002, 0008, 0010, 0012. Issues #13 (seams) and #14 (mapper).
- Code:
  - `src/tapesift/media/types.py`, `src/tapesift/warning_codes.py`;
  - `src/tapesift/cli/doctor.py` (`Profile`, `Probes.version_of`, `diagnose`, `render`, `NETWORK_CALLS`) and `tests/unit/test_doctor.py` (`fake_probes`);
  - `tests/unit/test_media_types.py` (the subprocess import-check pattern);
  - `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml` (`uv sync --locked --all-extras`).
- **Observed by the planner on 2026-10-19:**
  - **HF API** (metadata only): the SHAs, licences and file lists in the pin table. `BAAI/bge-small-en-v1.5` also contains `pytorch_model.bin` (pickle).
  - **huggingface-hub 2.2.0 source:**
    - `snapshot_download(repo_id, *, revision, etag_timeout=10, local_files_only, allow_patterns, ...)`;
    - with `local_files_only=True` and nothing cached, it raises `huggingface_hub.errors.LocalEntryNotFoundError` (a `FileNotFoundError`);
    - per-request download timeout `HF_HUB_DOWNLOAD_TIMEOUT` (default 10 s); `hf-xet` is a dependency.
  - **faster-whisper 1.2.1:**
    - `WhisperModel` accepts a local directory, so `fetch_pin`'s path bypasses its own `download_model`;
    - `faster_whisper.vad.get_speech_timestamps(audio, VadOptions, sampling_rate)` returns sample spans and runs `assets/silero_vad_v6.onnx` on onnxruntime;
    - `Segment` and `Word` carry `avg_logprob` and `probability`.
  - **transformers 5.20.2:** SmolVLM needs `num2words` (card 7); the image backend falls back to PIL when torchvision is missing.
  - **CPU torch source (finding 2), on a scratch project with this spec's dependencies:**
    - `uv lock` downloaded metadata only: a 38 MB cache, no wheel over 5 MB. download.pytorch.org serves PEP 658 `data-core-metadata` for every `2.14.1+cpu` wheel.
    - The lock had `torch 2.14.1+cpu` (from `https://download.pytorch.org/whl/cpu`) for `sys_platform == 'linux'`, `torch 2.14.1` (PyPI) for everything else, and **zero** `nvidia-*` or `triton` packages.
    - `uv lock --check` passed.
    - The built wheel's METADATA says `Requires-Dist: torch>=2.14.1 ; extra == 'vision'`, with no index. So end users are unaffected.
    - For end users: `uv pip compile --torch-backend cpu` resolves `torch==2.14.1+cpu` on Linux, and without it the same input pulls 19 `nvidia-*`/`cuda-*`/`triton` packages. `uv tool install` and `uvx` both accept `--torch-backend` (uv 0.11.27).
  - **Fixture audio envelopes** (20 ms frame RMS, first chunk, decoded with `PyAVDecoder`, no models). These pin `FakeVAD`:

    | Fixture | max RMS | CV (std/mean) |
    | --- | --- | --- |
    | speech.mp4 | 0.2702 | 0.902 |
    | music.m4a | 0.0681 | 0.314 |
    | av_mismatch.mp4 | 0.1109 | 0.023 |
    | clean.mp4 | 0.1109 | 0.020 |
    | silence.mp4 | 0.0000 | 0 |

    speech.mp4's voiced spans (RMS ≥ 0.01, gaps < 0.3 s merged) are `(0.00, 2.82)` and `(3.20, 6.60)`. Its audio ends at 6.9925 s, and `duration_s` is 7.0.
  - **pydantic 2.14.1:** the exact error messages pinned in `test_config.py`, from a scratch model with the same fields.
  - **pytest:** without `pythonpath = ["."]`, `uv run pytest` fails collection on `from tests.fakes import ...`.
  - **Baseline on main at 989f5c1:**
    - `uv run pytest -q -m "not gpu"`: `451 passed, 2 deselected`;
    - `tests/unit/test_doctor.py`: `31 passed`;
    - `ruff format --check`: `51 files already formatted`.

## Scope
May change:
- New files:
  - `src/tapesift/{schema,audio,vision,store}/__init__.py`: one-line docstrings;
  - `src/tapesift/schema/records.py`, `src/tapesift/audio/types.py`, `src/tapesift/vision/types.py`, `src/tapesift/store/types.py`, `src/tapesift/config.py`, `src/tapesift/hub.py`;
  - `tests/fakes.py`;
  - `tests/contract/test_{asr,vad,vlm,embedder,store}.py`;
  - `tests/unit/test_records.py`, `tests/unit/test_config.py`, `tests/unit/test_hub.py`;
  - `tests/smoke/test_record_boundaries.py`.
- `src/tapesift/cli/doctor.py`:
  - `Profile` moves to config.py (import it back);
  - `Report` gains `vision: str | None` after `torchcodec`;
  - `diagnose` fills it and adds the note;
  - `render` adds the `vision` line.

  Exact behaviour is in Interfaces. Nothing else changes.
- `tests/unit/test_doctor.py`: add 2 tests. Nothing removed or edited.
- `pyproject.toml`:
  - the dependencies;
  - `[[tool.uv.index]]` and `[tool.uv.sources]` for CPU torch on Linux;
  - jsonschema (dev);
  - the `model` marker;
  - `pythonpath = ["."]`.
- `uv.lock`: regenerated by `uv add` / `uv lock` only.
- `Makefile`: the `test` recipe becomes `uv run pytest -q -m "not gpu and not model"`.
- `THIRD_PARTY.md`: the rows below.
- `AGENTS.md`: card 9's two lane lines, exactly. The Core line is replaced and the Interfaces line added after it; nothing else changes (owner-approved context edit, 2026-10-20).
- `docs/spec.md`: the places listed in "docs/spec.md edits", exactly, including card 10's lines 198 and 206.
- `CHANGELOG.md`: one line under Unreleased, Added: `- Shared v0.1 interfaces: result records, the ASR, VAD, VLM, Embedder and Store protocols, config.py with pinned models, shared test fakes; faster-whisper, LanceDB, pydantic and onnxruntime become dependencies, and captions need the new "tapesift[vision]" extra (#25).`

Must not touch:
- `src/tapesift/media/**`, `src/tapesift/warning_codes.py`, `src/tapesift/cli/__init__.py`
- Every stage implementation: `audio/{stage,faster_whisper,vad,phantoms}.py`, `vision/{stage,transformers_vlm,prompts,embed}.py`, `store/lance.py`, `schema/output.py`, `runner/`, `pipeline/`, `eval/`
- `.github/workflows/**` (E3 adds the `models` job; `ci.yml` picks up CPU torch through the lock with no edit), `tests/fixtures/**`, `scripts/**`, existing tests other than the 2 additions, `README.md` (E9), `CLAUDE.md`, `.claude/**`

## Interfaces touched
Before: nothing; the only definition is the illustrative block in docs/spec.md. After: the files below, exactly. Docstrings and comments are part of the contract.

### `src/tapesift/schema/records.py`
```python
"""Result records shared by the stages (E3, E4), the schema mapper (E5), the store (E6) and the
runner (E7). Frozen stdlib dataclasses (M0 card); E5 maps them to schema 1.0 JSON. Rules: M1
R1-R3. Imports nothing heavier than tapesift.media.types (numpy)."""

from __future__ import annotations

import dataclasses
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Final, Literal

from tapesift.media.types import AssetInfo
from tapesift.warning_codes import AssetWarning

BACKEND_ID_RE: Final = re.compile(r"[a-z0-9-]+:[^\s@]+@(?:[0-9a-f]{40}|unpinned)")
"""Use with fullmatch. "<backend>:<model>@<revision>" (card 6). The revision is the full 40-hex
commit SHA, or exactly "unpinned" for an endpoint backend that reports none."""


def _check_span(what: str, start_s: float, end_s: float) -> None:
    if not (math.isfinite(start_s) and math.isfinite(end_s) and 0.0 <= start_s <= end_s):
        raise ValueError(f"{what}: need finite 0 <= start_s <= end_s, got {start_s}, {end_s}")


def _check_conf(what: str, conf: float) -> None:
    if not 0.0 <= conf <= 1.0:  # also rejects NaN
        raise ValueError(f"{what}: conf must be in [0, 1], got {conf}")


@dataclass(frozen=True, slots=True)
class Word:
    """schema: utterances[].words[] = {"w", "start_s", "end_s"}."""

    w: str
    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        _check_span("Word", self.start_s, self.end_s)


@dataclass(frozen=True, slots=True)
class Utterance:
    """schema: utterances[]. Times are seconds on the container clock (M0 R1)."""

    start_s: float
    end_s: float
    text: str
    lang: str | None  # ISO 639-1 code the ASR detected, e.g. "en"; None if none (card 5)
    conf: float  # in [0, 1]; how it is derived is E3's spec
    words: tuple[Word, ...]  # sorted by start_s, each inside [start_s, end_s]; may be empty

    def __post_init__(self) -> None:
        _check_span("Utterance", self.start_s, self.end_s)
        _check_conf("Utterance", self.conf)
        starts = [w.start_s for w in self.words]
        if starts != sorted(starts) or any(
            w.start_s < self.start_s or w.end_s > self.end_s for w in self.words
        ):
            raise ValueError("Utterance.words must be sorted and inside the utterance")


@dataclass(frozen=True, slots=True)
class Caption:
    """schema: captions[]. No `shot` field: E5 writes "shot": null in v0.1 (card 2)."""

    t_s: float  # the captioned Frame's t_s
    text: str
    conf: float | None  # in [0, 1]; None when the backend cannot compute one (card 2)
    media_text: tuple[str, ...]  # words the VLM read in the frame; untrusted (spec Y1)

    def __post_init__(self) -> None:
        _check_span("Caption", self.t_s, self.t_s)
        if self.conf is not None:
            _check_conf("Caption", self.conf)


@dataclass(frozen=True, slots=True)
class Provenance:
    """schema: provenance. A stage that did not run has None (card 6)."""

    tapesift: str  # tapesift.__version__
    asr: str | None  # ASR.id; None when ASR did not run (no audio, LOW_SPEECH, StageError)
    vlm: str | None  # VLM.id; None when captioning did not run (no video, captions off, ...)
    prompt: str | None  # prompt id, e.g. "caption_v1"; set exactly when vlm is set

    def __post_init__(self) -> None:
        for name, value in (("asr", self.asr), ("vlm", self.vlm)):
            if value is not None and not BACKEND_ID_RE.fullmatch(value):
                raise ValueError(f"Provenance.{name} is not a backend id: {value!r}")
        if (self.vlm is None) != (self.prompt is None):
            raise ValueError("Provenance.vlm and Provenance.prompt are set together")


@dataclass(frozen=True, slots=True)
class AssetRecord:
    """Everything known about one asset: what E5 serializes, E6 indexes and E7 writes.
    Strict on purpose: stages clamp first (R2), so a raise here is a programmer bug."""

    asset: AssetInfo
    utterances: tuple[Utterance, ...]  # sorted by start_s
    captions: tuple[Caption, ...]  # t_s strictly increasing
    warnings: tuple[AssetWarning, ...]  # normalized on construction: union with asset.warnings,
    # deduplicated, sorted by (code, detail)
    provenance: Provenance

    def __post_init__(self) -> None:
        merged = set(self.warnings) | set(self.asset.warnings)
        object.__setattr__(
            self, "warnings", tuple(sorted(merged, key=lambda w: (w.code.value, w.detail)))
        )
        starts = [u.start_s for u in self.utterances]
        times = [c.t_s for c in self.captions]
        if starts != sorted(starts) or any(b <= a for a, b in pairwise(times)):
            raise ValueError("AssetRecord: utterances sorted, caption t_s strictly increasing")
        d = self.asset.duration_s
        if d is not None and (
            any(u.end_s > d for u in self.utterances) or any(c.t_s >= d for c in self.captions)
        ):
            raise ValueError(f"AssetRecord: a time is past duration_s {d}")


def clamp_utterance(u: Utterance, lo: float, hi: float) -> Utterance | None:
    """Fit an ASR utterance into [lo, hi] (R2): the stage passes lo = the chunk start and
    hi = min(chunk end, duration_s). None when nothing is left (u.start_s >= hi or u.end_s < lo).
    Otherwise start = clamp(u.start_s), end = clamp(max(u.end_s, start)), and each word is clamped
    into [start, end] the same way; a word with w.start_s >= hi or w.end_s < lo is dropped.
    Never raises on overshoot; ValueError only when lo, hi are not finite with 0 <= lo <= hi."""

    _check_span("clamp_utterance bounds", lo, hi)

    def c(t: float, a: float, b: float) -> float:
        return min(max(t, a), b)

    if u.start_s >= hi or u.end_s < lo:
        return None
    s = c(u.start_s, lo, hi)
    e = c(u.end_s, s, hi)
    words = tuple(
        Word(w.w, ws := c(w.start_s, s, e), c(w.end_s, ws, e))
        for w in u.words
        if w.start_s < hi and w.end_s >= lo
    )
    return dataclasses.replace(u, start_s=s, end_s=e, words=words)


class Modality(StrEnum):
    """What a search hit matched. The CLI's --modality any is modality=None. Consumers of
    --json must tolerate values added later (card 3)."""

    SPEECH = "speech"  # an utterance
    VISUAL = "visual"  # a caption


@dataclass(frozen=True, slots=True)
class Hit:
    """One search result (card 3). `tapesift search --json` prints
    {"query": <q>, "hits": [dataclasses.asdict(h) for h in hits]}."""

    asset_id: str
    path: str  # str(AssetInfo.path) as indexed
    start_s: float
    end_s: float  # == start_s for VISUAL: a caption is a point in time
    modality: Modality
    text: str  # the utterance text, or the caption text (never the on-screen words)
    media_text: tuple[str, ...]  # VISUAL: the caption's on-screen words; SPEECH: ()
    score: float  # higher is better within one query; never compare across queries (v0.1: cosine)
    trust: Literal["untrusted_media"] = "untrusted_media"  # every hit is media text (Y1, S8)
```

### `src/tapesift/audio/types.py`
```python
"""The VAD and ASR backend Protocols. E3 implements them (Silero via faster_whisper.vad, and
faster-whisper); tests use tests/fakes.py."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from tapesift.media.types import AudioChunk
from tapesift.schema.records import Utterance


class VAD(Protocol):
    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]:
        """Speech regions of one chunk as (start_s, end_s) on the container clock: sorted,
        non-overlapping, inside [chunk.start_s, chunk end]. [] when the chunk has no speech."""
        ...


class ASR(Protocol):
    @property
    def id(self) -> str:
        """Backend id for provenance; matches BACKEND_ID_RE."""
        ...

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        """One list per chunk, in order, each sorted by start_s. Chunks are independent: they
        may overlap or leave gaps (the stage's seam handling, R8). Times are on the container
        clock (the backend adds chunk.start_s). Starts are inside the chunk; ends may overshoot
        the chunk end by up to 1.0 s (Whisper rounds segment ends), and the stage clamps (R2).
        No VAD gating here. Any exception is a backend failure (R5)."""
        ...
```

### `src/tapesift/vision/types.py`
```python
"""The VLM and text Embedder Protocols. E4 implements VLM (transformers, vision extra); E6
implements Embedder (ONNX, vision/embed.py). Importing this module never imports torch (R6)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from tapesift.media.types import Frame
from tapesift.schema.records import Caption


class VLM(Protocol):
    @property
    def id(self) -> str:
        """Backend id for provenance; matches BACKEND_ID_RE."""
        ...

    def caption(self, frames: Sequence[Frame], prompt_id: str) -> list[Caption]:
        """One Caption per frame, in order, with caption.t_s == frame.t_s. The caller batches
        (len(frames) <= vlm.max_batch). An unknown prompt_id raises ValueError."""
        ...


class Embedder(Protocol):
    """Text only until S3 (card 8)."""

    @property
    def id(self) -> str:
        """Backend id; matches BACKEND_ID_RE."""
        ...

    @property
    def dim(self) -> int: ...

    def embed_text(
        self, texts: Sequence[str], *, kind: Literal["query", "passage"]
    ) -> NDArray[np.float32]:
        """Shape (len(texts), dim), float32; every row has L2 norm 1 within 1e-5, "" included.
        kind="query" for search queries, "passage" for indexed text (bge adds its query prefix).
        A text longer than the model's limit is truncated to it, never rejected. Deterministic."""
        ...
```

### `src/tapesift/store/types.py`
```python
"""The search store Protocol. E6 implements it (LanceDB); tests use tests/fakes.MemoryStore."""

from __future__ import annotations

from typing import Protocol

from tapesift.schema.records import AssetRecord, Hit, Modality


class Store(Protocol):
    def upsert(self, record: AssetRecord) -> None:
        """Replace every row of record.asset.id with one SPEECH row per utterance and one VISUAL
        row per caption. A VISUAL row is embedded from caption.text and its media_text,
        space-joined (so on-screen words are searchable); its Hit keeps them in separate fields.
        Rows are embedded with kind="passage". Idempotent."""
        ...

    def delete(self, asset_id: str) -> None:
        """Remove every row of asset_id. Unknown ids are a no-op. E7 calls it when a path it
        indexed before now has a different asset id (the file changed)."""
        ...

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        modality: Modality | None = None,
        asset_id: str | None = None,
    ) -> list[Hit]:
        """At most k hits by score, descending; ties by (asset_id, start_s) ascending. The query
        is embedded with kind="query". modality None means both (the CLI's "any"); asset_id
        restricts to one asset (--asset). k < 1 raises ValueError. An empty store returns []."""
        ...
```

### `src/tapesift/config.py`
```python
"""Configuration (spec, CLI and config): these pydantic models are the only home of defaults.
Also the model pins (owner Q3, 2026-10-19), Profile (moved from cli/doctor.py), the vision-extra
check and the two errors the CLI maps to exit codes. Imports pydantic and the stdlib only."""

from __future__ import annotations

import importlib.util
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_FILENAME: Final = "tapesift.toml"


class Profile(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    SERVER = "server"


class ConfigError(ValueError):
    """Bad config file or value. The message names every bad key; the CLI exits 2."""


class ModelLoadError(RuntimeError):
    """A real backend cannot load its pinned model: not cached while offline, download failed,
    or the vision extra missing. Raised by fetch_pin and backend constructors; the CLI exits 3."""


def vision_available() -> bool:
    """True when the vision extra's runtime is importable (transformers and torch)."""
    return all(importlib.util.find_spec(m) is not None for m in ("transformers", "torch"))


@dataclass(frozen=True, slots=True)
class ModelPin:
    backend: str  # "faster-whisper", "transformers" or "onnx"
    name: str  # the config value, e.g. "small"
    repo: str  # Hugging Face repo id
    revision: str  # full 40-hex commit SHA, from the HF API on 2026-10-19
    files: tuple[str, ...]  # the only files fetch_pin fetches; never a pickle (R4)

    @property
    def id(self) -> str:
        """The backend id for provenance: "<backend>:<name>@<revision>"."""
        return f"{self.backend}:{self.name}@{self.revision}"


_WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")  # CTranslate2
ASR_MODELS: Final[dict[str, ModelPin]] = {
    "small": ModelPin("faster-whisper", "small", "Systran/faster-whisper-small",
                      "536b0662742c02347bc0e980a01041f333bce120", _WHISPER_FILES),
    "tiny": ModelPin("faster-whisper", "tiny", "Systran/faster-whisper-tiny",
                     "d90ca5fe260221311c53c58e660288d3deb8d356", _WHISPER_FILES),
}  # fmt: skip
VLM_MODELS: Final[dict[str, ModelPin]] = {
    "smolvlm2-256m": ModelPin(
        "transformers", "smolvlm2-256m", "HuggingFaceTB/SmolVLM2-256M-Video-Instruct",
        "067788b187b95ebe7b2e040b3e4299e342e5b8fd",
        ("added_tokens.json", "chat_template.json", "config.json", "generation_config.json",
         "merges.txt", "model.safetensors", "preprocessor_config.json", "processor_config.json",
         "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.json"),
    ),
}  # fmt: skip
EMBEDDER: Final = ModelPin("onnx", "bge-small-en-v1.5", "BAAI/bge-small-en-v1.5",
                           "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
                           ("onnx/model.onnx", "tokenizer.json"))  # fmt: skip


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SamplingConfig(_Section):
    strategy: Literal["fixed"] = "fixed"  # "shots+dedupe" arrives with C3 (v0.2)
    fixed_fps: float = Field(default=1.0, gt=0)


class AsrConfig(_Section):
    backend: Literal["faster-whisper"] = "faster-whisper"
    model: Literal["small", "tiny"] = "small"  # keys of ASR_MODELS
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    vad_min_speech_ratio: float = Field(default=0.05, ge=0.0, le=1.0)  # below: skip ASR
    batch_seconds: float = Field(default=600.0, gt=0)  # Decoder.iter_audio chunk_s
    audio_track: int | None = Field(default=None, ge=0)  # index into AssetInfo.audio


class VlmConfig(_Section):
    backend: Literal["auto", "transformers", "none"] = "auto"  # "openai" arrives with C6
    model: Literal["smolvlm2-256m"] = "smolvlm2-256m"  # keys of VLM_MODELS
    max_batch: int | None = Field(default=None, ge=1)  # None: VLM_MAX_BATCH[profile] (card 4)
    prompt: Literal["caption_v1"] = "caption_v1"


class StoreConfig(_Section):
    backend: Literal["lancedb"] = "lancedb"


class Config(_Section):
    profile: Profile | None = None  # None: E7 fills it from doctor's pick_profile
    out_dir: Path = Path("tapesift_index")  # relative to the current directory
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    vlm: VlmConfig = Field(default_factory=VlmConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)


VLM_MAX_BATCH: Final[dict[Profile, int]] = {Profile.CPU: 8, Profile.GPU: 8, Profile.SERVER: 8}
"""Per-profile default for vlm.max_batch in v0.1; C6 raises gpu and server (card 4)."""

_PATH_KEYS: Final = (("out_dir",),)
"""Every Path-typed key, as a key path into the file's table. A relative value written in a
config file resolves against that file's folder (card 4). A test keeps this list complete."""


def vlm_max_batch(cfg: Config) -> int:
    """cfg.vlm.max_batch if set, else VLM_MAX_BATCH[cfg.profile], with None treated as cpu."""
    if cfg.vlm.max_batch is not None:
        return cfg.vlm.max_batch
    return VLM_MAX_BATCH[cfg.profile or Profile.CPU]


def load_config(
    path: Path | None = None, *, profile: Profile | None = None, out_dir: Path | None = None
) -> Config:
    """Defaults < file < flags. path is --config; None means ./tapesift.toml if it is a file,
    else no file. A flag that is not None overrides the file. Raises ConfigError (R7)."""
```
`load_config` behaviour (R7):
1. If `path is None` and `Path(CONFIG_FILENAME).is_file()`, then `path = Path(CONFIG_FILENAME)`.
2. If `path` is set, `data = tomllib.loads(path.read_text(encoding="utf-8"))`.
   - `FileNotFoundError` becomes `ConfigError(f"{path}: file not found")`.
   - Any other `OSError`, `UnicodeDecodeError` or `tomllib.TOMLDecodeError` `e` becomes `ConfigError(f"{path}: {e}")`.
3. **Path keys.** For each key path in `_PATH_KEYS` that is present in `data` as a string: if `Path(value)` is relative, replace it with `str(path.parent / value)`. An absolute value is kept. So `./tapesift.toml` resolves against `.`, and `--config conf/t.toml` with `out_dir = "idx"` gives `conf/idx`.
4. `profile` and `out_dir` (the `--out` flag), when not None, overwrite `data["profile"]` and `data["out_dir"]` after step 3, unresolved. Flags and the default stay relative to the current directory.
5. `Config.model_validate(data)`. A `ValidationError` becomes `ConfigError`, raised `from None`, with this message:
   - the prefix is `f"{path}: "` when a file was read, else nothing;
   - then `"; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())`.

### `src/tapesift/hub.py`
```python
"""The one place that fetches model files (R4). Imports huggingface_hub inside fetch_pin only."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tapesift.config import ModelLoadError, ModelPin

HUB_ETAG_TIMEOUT_S: Final = 10.0  # per metadata request; each file read also times out after
# huggingface_hub's HF_HUB_DOWNLOAD_TIMEOUT (default 10 s)


def fetch_pin(pin: ModelPin) -> Path:
    """Local snapshot directory holding every name in pin.files at pin.revision."""
```
`fetch_pin` behaviour. It calls `huggingface_hub.snapshot_download` through the module attribute, so tests can patch it.
1. `d = snapshot_download(pin.repo, revision=pin.revision, allow_patterns=list(pin.files), local_files_only=True)`. If every `d / name` in `pin.files` exists, return `Path(d)`. No network is used.
2. On `huggingface_hub.errors.LocalEntryNotFoundError`, or a file missing in step 1, make the same call with `local_files_only=False, etag_timeout=HUB_ETAG_TIMEOUT_S`. Any exception from this call becomes `ModelLoadError(f"cannot fetch {pin.repo}@{pin.revision[:12]}: {type(e).__name__}: {e}")`.
3. If any name in `pin.files` is missing under the result, raise `ModelLoadError(f"{pin.repo}@{pin.revision[:12]}: missing {name}")`.

Backends then load only from the returned directory, with local-only flags: transformers `from_pretrained(d, local_files_only=True, trust_remote_code=False)`; faster-whisper `WhisperModel(str(d), ...)`; `onnxruntime.InferenceSession(d / "onnx/model.onnx")` and `tokenizers.Tokenizer.from_file(d / "tokenizer.json")`.

### `src/tapesift/cli/doctor.py`
- `class Profile(StrEnum)` is deleted and replaced by `from tapesift.config import Profile`, so `tapesift.cli.doctor.Profile is tapesift.config.Profile`.
- `Report` gains `vision: str | None` directly after `torchcodec`.
- In `diagnose`, with `t = probes.version_of("transformers")` and `tv = probes.version_of("torch")`:
  - `vision = f"transformers {t}, torch {tv}" if t and tv else None`;
  - when it is None, append the note `'vision extra not installed: index skips captions; install "tapesift[vision]"'`.
- `render` adds `f"vision       {report.vision or 'not installed (index skips captions)'}"` after the torchcodec line.

`doctor --json` gains the key `"vision"`.

### Stage entry points and real backends (fixed here; E3-E6 write them, E7 calls them)
```python
# src/tapesift/audio/stage.py (E3)
def transcribe_asset(
    asset: AssetInfo, decoder: Decoder, vad: VAD, asr: ASR, cfg: Config, *, warn: WarningSink
) -> list[Utterance]:
    """R8. Sorted by start_s; consecutive utterances overlap by at most 0.1 s; every time inside
    [0, duration_s] (clamped, R2). [] when asset.audio is empty. Speech ratio from vad below
    cfg.asr.vad_min_speech_ratio: [] and LOW_SPEECH via warn, and asr.transcribe is never called.
    Track: cfg.asr.audio_track, else the default. StageError (e.g. DecodeError) propagates."""

# src/tapesift/vision/stage.py (E4)
def caption_asset(
    asset: AssetInfo, decoder: Decoder, vlm: VLM, cfg: Config, *, warn: WarningSink
) -> list[Caption]:
    """One caption per frame of decoder.iter_frames(asset, 1 / cfg.sampling.fixed_fps,
    warn=warn), in batches of at most vlm_max_batch(cfg), prompt cfg.vlm.prompt. [] when
    asset.video is None. MEDIA_TEXT via warn when any caption has media_text."""

# src/tapesift/schema/output.py (E5)
SCHEMA_VERSION: Final = "1.0"
def to_json(record: AssetRecord) -> dict[str, object]: ...

# Real backends. Each constructor calls fetch_pin (R4) and raises ModelLoadError when it can't
# load. E7 imports these modules lazily (R6).
class SileroVAD:         # src/tapesift/audio/vad.py (E3); bundled ONNX, no fetch, no model marker
    def __init__(self, cfg: Config) -> None: ...
class FasterWhisperASR:  # src/tapesift/audio/faster_whisper.py (E3); ASR_MODELS[cfg.asr.model]
    def __init__(self, cfg: Config) -> None: ...
class TransformersVLM:   # src/tapesift/vision/transformers_vlm.py (E4, vision extra); VLM_MODELS[...]
    def __init__(self, cfg: Config) -> None: ...  # ModelLoadError if not vision_available();
    # installs the guarded num2words shim (card 7) before building the processor
class OnnxEmbedder:      # src/tapesift/vision/embed.py (E6); EMBEDDER
    def __init__(self, cfg: Config) -> None: ...
class LanceStore:        # src/tapesift/store/lance.py (E6); opens or creates cfg.out_dir / "store"
    def __init__(self, cfg: Config, embedder: Embedder) -> None: ...
```

### Rules
Each rule ends with "Tested by", naming the PR whose tests cover it.

**R1. Clock.** Every record time is seconds on the container clock (M0 R1):
- ASR and VAD backends add `chunk.start_s`;
- a caption's `t_s` is its frame's `t_s`;
- E5 never re-times anything.

Tested by: M1 (contract `test_times_on_container_clock`, `test_spans_inside_chunk_sorted`), E3, E4.

**R2. Records are strict; stages clamp.**
- Record constructors raise `ValueError` on any of these:
  - a non-finite or reversed span;
  - a `conf` outside [0, 1];
  - a word outside its utterance;
  - unsorted utterances, or caption times that don't strictly increase;
  - a time past `duration_s`.
- So no real-world imprecision reaches them:
  - **backends** build each `Utterance` with its words clamped into the segment (Whisper word times can spill past their segment);
  - **E3's stage** passes every utterance through `clamp_utterance(u, chunk.start_s, min(chunk end, asset.duration_s))`, dropping None results. On av_mismatch.mp4 the decoder trims audio at `duration_s` (M0 R1), and Whisper's 20 ms end rounding can still land past it; the clamp absorbs that.
  - Captions need no clamp: frames already have `t_s < duration_s` (M0 R7).
- **Tolerance.** Clamping always succeeds. E3 logs one WARNING per asset when any clamp moved a time by more than 0.5 s, because that size means a backend bug, not media.
- A `ValueError` from a record therefore means a programmer bug, and R5 fails that one asset, never the batch.

Tested by: M1 (`test_clamp_utterance`, `tests/smoke/test_record_boundaries.py`); E3.

**R3. Backend ids** fullmatch `BACKEND_ID_RE`. A real backend's `id` is its `ModelPin.id` (40-hex revision). A fake's is `"fake:<role>@" + "0" * 40`. Endpoint backends (C6) use exactly `unpinned` when the server reports no revision. Tested by: M1.

**R4. Models.** Every pinned model is fetched through `tapesift.hub.fetch_pin`:
- only `pin.files`, at `pin.revision`;
- cache-first with no network;
- timeouts on every request;
- `ModelLoadError` on failure.

Loading is local-only from the returned directory (see `fetch_pin`). Never a pickle, never `trust_remote_code=True`, no telemetry. The only network calls are huggingface.co fetches (doctor's `NETWORK_CALLS`, Y3). A changed pin needs a card, and THIRD_PARTY.md changes in the same PR. transformers is pinned exactly (`==5.20.2`) because E4's num2words shim (card 7) depends on a private module global; upgrading it needs a card and a re-check of `hasattr`. Tested by: M1 (`test_hub.py`, `test_model_pins`); E3, E4 and E6 (real loads in the `models` job).

**R5. Per-file failures** (card 1 C), applied by E7:
- **`ProbeError`:** no record and no marker, because the file has no ID. The summary line carries the code.
- **A `StageError` from `transcribe_asset` or `caption_asset`:** that stage contributes nothing and its provenance entry is None; its `.warning` goes on the record; the other stage still runs; the record is written.
- **Any other exception** from a stage, a record constructor, `to_json`, `Store.upsert`/`delete` or the file write: the asset fails.
  - No JSON is written (the JSON is written last and atomically, after the upsert).
  - E7 writes the failed marker and applies the retry cap from card 1.
  - The batch continues.
- The exit code is 1 when at least one asset failed or was skipped as failed before.
- A `ModelLoadError` during backend construction (before any file) exits 3. A `ConfigError` exits 2.

Tested by: E7.

**R6. Imports.**
- Importing `tapesift.config`, `tapesift.hub`, `tapesift.schema.records`, `tapesift.audio.types`, `tapesift.vision.types` or `tapesift.store.types` imports none of `torch`, `transformers`, `ctranslate2`, `faster_whisper`, `lancedb`, `pyarrow`, `onnxruntime`, `tokenizers`, `huggingface_hub`, `av`.
- E7 imports real backend modules inside the function that builds them, so `tapesift --version`, `doctor` and `search` never load torch, and a missing `vision` extra fails only where captions are built.

Tested by: M1 (`test_interface_modules_import_no_backends`); E7.

**R7. Config.**
- Precedence is flag > file > default.
- A relative path written in a file resolves against that file's folder. `--out` and the default resolve against the current directory.
- `vlm.max_batch` unset means `vlm_max_batch(cfg)`.
- `--config FILE` on `index` and `search` is `load_config(path=FILE)`; it is wired by E7 and E6.
- Unknown keys and bad values raise `ConfigError` naming the dotted key (card 4).
- `profile` picks the device: CUDA only for `gpu` or `server`.

Tested by: M1 (`test_config.py`); E6 and E7 (flags, exit 2).

**R8. Audio stage contract (E3).**
- **Streaming.** `transcribe_asset` holds at most one decoded chunk plus its seam overlap at a time, and calls `asr.transcribe` with chunks of this asset only.
- **E3 must (a required E3 acceptance item; owner, 2026-10-20).** A tracemalloc test runs `transcribe_asset` with `FakeVAD`, `FakeASR` and a decoder stub that yields at least 6 synthetic 600 s chunks (one hour or more). Its peak must stay under a bound E3 pins, independent of length: about 2 chunks (2 × 38.4 MB) plus fixed overhead. A run with twice as many chunks must have the same peak within 10%.
- **VAD.** The `vad` parameter is the only speech detector: it is used for the `LOW_SPEECH` ratio and may drive seam cuts. Laptop tests may run `SileroVAD` (owner Q5).
- **Seams (#13, M0 audio card).** Each spoken word appears once in the output. E3 picks VAD-aligned cuts or overlap-and-dedupe, and its `chunk_s=2.0` run on speech.mp4 must meet the WER bound.
- Consecutive utterances overlap by at most 0.1 s.

Tested by: E3.

**R9. Captions off is visible.** `vlm.backend` resolves as follows (E7):
- `"auto"` becomes `"transformers"` when `vision_available()`. Otherwise it becomes `"none"` and logs one WARNING per run: `captions off: install "tapesift[vision]"`.
- An explicit `"transformers"` without the extra raises `ModelLoadError` (exit 3), naming `tapesift[vision]`.
- An explicit `"none"` logs one INFO line: `captions off (vlm.backend = "none")`.

With captions off, `provenance.vlm` and `prompt` are null, `captions` is `[]`, and no warning code is added. `doctor` prints the `vision` line and note. Tested by: M1 (doctor tests, `test_vision_available`); E7 (the log lines).

### Fakes (`tests/fakes.py`)
Deterministic, numpy and stdlib only. Each fake satisfies its Protocol under pyright (the contract fixtures are typed as the Protocol).

| Fake | Behaviour |
| --- | --- |
| `FakeVAD()` | Frames of `n = sample_rate // 50` samples (20 ms); `r` = frame RMS over `len(samples) // n` frames. A chunk is speech-like iff it has at least 1 frame, `r.max() >= 0.01` and `r.std() / r.mean() >= 0.5`. A steady tone or chord has a flat envelope (fixtures: CV 0.020-0.314) and gives `[]`; speech.mp4 has CV 0.902. For a speech-like chunk, the spans are the voiced frames (`r >= 0.01`) on the container clock, with gaps under 0.3 s merged. |
| `FakeASR(overshoot_s=0.0)` | `id = "fake:asr@" + "0" * 40`; `calls: list[int]` records `len(chunks)`. For each chunk, one `Utterance` per `FakeVAD` span `(s, e)`, with text `"fake speech"`, lang `"en"`, conf `1.0`, and words `("fake", s, m)` and `("speech", m, e2)`, where `m = (s + e) / 2` and `e2 = e + overshoot_s` is also the utterance end. `overshoot_s` imitates Whisper's end overshoot; the default 0 keeps every time inside the chunk. So a tone or silence gives `[]`, as the real VAD-plus-ASR path does. |
| `FakeVLM()` | `id = "fake:vlm@" + "0" * 40`; `calls: list[int]`. A `prompt_id` other than `"caption_v1"` raises `ValueError`. Each frame gives `Caption(f.t_s, f"fake caption {w}x{h}", 1.0, ())`. |
| `FakeEmbedder(dim=256)` | `id = "fake:embedder@" + "0" * 40`; `calls: list[int]`. `kind` is accepted and ignored. Tokens are `re.findall(r"[a-z0-9]+", text.lower())[:512]` (the fake's truncation). Each token adds 1.0 at `int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big") % dim`. An all-zero row becomes 1.0 at index 0. Rows are L2-normalized and float32. |
| `MemoryStore(embedder: Embedder)` | A list of rows `(asset_id, path, modality, start_s, end_s, text, media_text, vector)`, following the `Store` docstrings: upsert replaces, delete removes, search embeds the query with `kind="query"`, scores by dot product, filters, sorts, then takes `[:k]`. |

### Contract tests (`tests/contract/`)
Each module has one fixture, `backend` (`store` in test_store.py), parametrized with `pytest.param(..., id="fake")`. Real backends join later and change nothing else:
- E3 adds `SileroVAD` with no marker (owner Q5), and `FasterWhisperASR` marked `model`;
- E4 adds `TransformersVLM`, marked `model`;
- E6 adds `OnnxEmbedder` and `LanceStore`, marked `model`.

Inputs are built in the module, never from fixture files:
- `AssetInfo` literals with IDs of the form `"tsid1:" + "0" * 64`;
- `BURSTS`: 2 s at 16 kHz made of four repeats of 0.3 s of a 440 Hz tone at amplitude 0.3 followed by 0.2 s of zeros;
- `TONE`: 2 s of a steady 440 Hz tone at amplitude 0.1;
- `ZEROS`: 2 s of zeros;
- 64x48 grey `Frame`s.

| Module | Test | Asserts |
| --- | --- | --- |
| test_vad.py | `test_spans_inside_chunk_sorted` | `BURSTS` at `start_s=600.0`: spans are sorted, non-overlapping, inside `[600.0, 602.0]`; the fake's are non-empty |
| | `test_silence_has_no_spans` | `ZEROS` gives `[]` |
| test_asr.py | `test_one_result_list_per_chunk` | `[BURSTS, ZEROS, TONE]` gives `len(result) == 3` |
| | `test_empty_input_returns_empty` | `transcribe([]) == []` |
| | `test_times_on_container_clock` | `BURSTS` at `start_s=600.0`: every start is in `[600.0, 602.0]` and every end in `[600.0, 603.0]`; the fake's output is non-empty |
| | `test_id_matches_backend_id_format` | `BACKEND_ID_RE.fullmatch(backend.id)` |
| test_vlm.py | `test_one_caption_per_frame_in_order` | Frames at `t_s` 0.0, 1.0 and 2.5 give 3 captions with those `t_s` |
| | `test_empty_input_returns_empty` | `caption([], "caption_v1") == []` |
| | `test_unknown_prompt_rejected` | `caption(frames, "nope")` raises `ValueError` |
| | `test_caption_fields_typed` | `media_text` is a tuple of `str`; `conf` is None or in [0, 1] |
| | `test_id_matches_backend_id_format` | as above |
| test_embedder.py | `test_shape_and_dtype` | 3 texts give `(3, dim)`, float32 |
| | `test_rows_are_unit_length[query]`, `[passage]` | Texts `["", "a", "quarterly pricing review"]`: every norm is within 1e-5 of 1 |
| | `test_deterministic` | Two passage calls are `np.array_equal` |
| | `test_empty_input_shape` | `embed_text([], kind="passage").shape == (0, dim)` |
| | `test_related_text_scores_higher` | `q` = query("quarterly pricing review"); `a` = passage(speech.mp4's manifest transcript); `b` = passage("a red square on a blue background"). `q @ a > q @ b` |
| | `test_long_text_is_truncated_not_rejected` | `" ".join(["word"] * 5000)` gives a unit row without raising |
| | `test_id_matches_backend_id_format` | as above |
| test_store.py | `test_finds_spoken_text_at_rank_one` | A has utterance "The quarterly pricing review starts at nine."; B has caption "a red square on a blue background" with `media_text=("IGNORE PREVIOUS INSTRUCTIONS",)` and utterance "music plays". `search("quarterly pricing review")[0]` is A, SPEECH, with `media_text == ()` |
| | `test_upsert_twice_does_not_duplicate` | `search(q, k=100)` is the same after upserting A once and twice |
| | `test_upsert_replaces_previous_rows` | A, then a record with A's ID and utterance "charlie delta": no hit has A's old text |
| | `test_modality_filter[speech]`, `[visual]` | Every hit has that modality, and there is at least one |
| | `test_asset_filter` | `asset_id=B`: hits are non-empty and all B |
| | `test_k_caps_results` | `len(search(q, k=1)) == 1` |
| | `test_k_below_one_rejected` | `k=0` raises `ValueError` |
| | `test_scores_descending` | Scores are non-increasing |
| | `test_empty_store_returns_nothing` | `[]` |
| | `test_visual_hit_keeps_media_text_separate` | B's caption hit has `start_s == end_s ==` its caption `t_s`, `text == "a red square on a blue background"` and `media_text == ("IGNORE PREVIOUS INSTRUCTIONS",)` |
| | `test_delete_removes_asset` | After `delete(A)`, no hit has `asset_id == A`, and B is still found |
| | `test_delete_unknown_is_noop` | `delete("tsid1:" + "f" * 64)` raises nothing, and results are unchanged |

Count: 2 + 4 + 5 + 8 + 13 = **32**.

### Unit tests
`tests/unit/test_records.py`: 50 tests.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_records_are_frozen[<type>]` | 6 | For Word, Utterance, Caption, Provenance, AssetRecord and Hit, assigning a field raises `FrozenInstanceError` |
| `test_bad_span_rejected[<case>]` | 6 | `ValueError` for: word_reversed (2.0, 1.0); word_negative; word_nan; utterance_inf_end; caption_negative_t; caption_nan_t |
| `test_conf_out_of_range_rejected[<case>]` | 4 | Utterance conf -0.01 and 1.01; Caption conf NaN and 1.5 |
| `test_caption_conf_may_be_none` | 1 | `Caption(1.0, "x", None, ())` is accepted |
| `test_words_must_sit_inside_their_utterance[<case>]` | 3 | word_before_start, word_after_end, words_unsorted |
| `test_asset_record_merges_and_sorts_warnings` | 1 | `asset.warnings == (B,)` and `warnings=(B, A)` give `(A, B)` |
| `test_asset_record_rejects_bad_timeline[<case>]` | 4 | utterances_unsorted; captions_equal_t; utterance_end_past_duration (5.01 with `duration_s` 5.0); caption_at_duration (5.0) |
| `test_asset_record_allows_unknown_duration` | 1 | `duration_s=None` accepts an utterance ending at 1e6 |
| `test_provenance_backend_id[<case>]` | 10 | Accepted: `faster-whisper:small@<40 hex>`, `onnx:bge-small-en-v1.5@<40 hex>`, `openai:Qwen/Qwen2-VL-2B-Instruct@unpinned`, `fake:asr@<40 zeros>`. Rejected with `ValueError`: `small@<40 hex>` (no backend); `faster-whisper:small` (no revision); `Faster-Whisper:small@unpinned` (uppercase backend); `faster-whisper:sm all@unpinned` (space); `faster-whisper:small@536b0662742c` (short SHA); `openai:m@Unpinned` (not the exact literal) |
| `test_provenance_vlm_and_prompt_set_together[<case>]` | 2 | vlm without prompt, and prompt without vlm |
| `test_hit_json_shape` | 1 | `json.dumps(asdict(Hit("tsid1:" + "0" * 64, "a b.mp4", 1.5, 1.5, Modality.VISUAL, "a slide", ("BUY NOW",), 0.5)))` equals exactly `'{"asset_id": "tsid1:<64 zeros>", "path": "a b.mp4", "start_s": 1.5, "end_s": 1.5, "modality": "visual", "text": "a slide", "media_text": ["BUY NOW"], "score": 0.5, "trust": "untrusted_media"}'` |
| `test_modality_values` | 1 | `["speech", "visual"]` |
| `test_records_pickle_round_trip` | 1 | An `AssetRecord` with one of everything is equal after a pickle round trip |
| `test_interface_modules_import_no_backends` | 1 | `subprocess.run([sys.executable, "-c", ...], timeout=60)` imports the 6 R6 modules and prints the sorted intersection of the R6 list with `sys.modules`. The output is `[]` |
| `test_clamp_utterance[<case>]` | 6 | Bounds are `[0.0, 3.0]` unless a case says otherwise. **inside**: u (1.0, 2.0) is returned equal. **end_overshoot**: u (2.5, 3.04) with words (2.5, 2.9) and (2.9, 3.04) gives (2.5, 3.0) and last word (2.9, 3.0). **start_before_lo**: bounds `[1.0, 3.0]`, u (0.5, 1.5) with words (0.5, 1.0) and (1.0, 1.5) gives (1.0, 1.5) and words (1.0, 1.0) and (1.0, 1.5). **word_past_hi_dropped**: u (2.0, 3.2) with words (2.0, 2.9) and (3.01, 3.2) gives (2.0, 3.0) and one word. **entirely_after**: u (3.0, 3.5) gives None. **entirely_before**: bounds `[1.0, 3.0]`, u (0.2, 0.5) gives None |
| `test_clamp_rejects_bad_bounds[<case>]` | 2 | `lo > hi`, and `hi` NaN, raise `ValueError` |

`tests/unit/test_config.py`: 36 tests. Writes go to `tmp_path`; discovery tests call `monkeypatch.chdir(tmp_path)`.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_defaults` | 1 | In an empty cwd, `load_config().model_dump(mode="json")` equals exactly `{"profile": None, "out_dir": "tapesift_index", "sampling": {"strategy": "fixed", "fixed_fps": 1.0}, "asr": {"backend": "faster-whisper", "model": "small", "compute_type": "int8", "vad_min_speech_ratio": 0.05, "batch_seconds": 600.0, "audio_track": None}, "vlm": {"backend": "auto", "model": "smolvlm2-256m", "max_batch": None, "prompt": "caption_v1"}, "store": {"backend": "lancedb"}}` |
| `test_empty_file_is_valid` | 1 | An empty file gives `== Config()` |
| `test_unknown_key_is_named[<case>]` | 4 | `str(e) == f"{p}: {loc}: Extra inputs are not permitted"` for `colour = 1` (`colour`), `[asr]` `modle = "x"` (`asr.modle`), `[safety]` `redact_pii = false` (`safety`), and `[sampling]` `shot_threshold = 27.0` (`sampling.shot_threshold`) |
| `test_bad_value_is_named[<case>]` | 8 | `str(e) == f"{p}: {loc}: {msg}"`: `asr.model = "large-v3-turbo"`, "Input should be 'small' or 'tiny'"; `sampling.strategy = "shots+dedupe"`, "Input should be 'fixed'"; `sampling.fixed_fps = 0`, "Input should be greater than 0"; `sampling.fixed_fps = inf`, "Input should be a finite number"; `asr.vad_min_speech_ratio = 1.5`, "Input should be less than or equal to 1"; `vlm.max_batch = 0`, "Input should be greater than or equal to 1"; `profile = "tpu"`, "Input should be 'cpu', 'gpu' or 'server'"; `asr.audio_track = -1`, "Input should be greater than or equal to 0" |
| `test_every_bad_key_is_reported` | 1 | `colour = 1` plus `[vlm]` `max_batch = 0` give one message containing both, separated by `"; "` |
| `test_toml_syntax_error` | 1 | `asr = [` raises `ConfigError` whose message starts with `f"{p}: "` |
| `test_explicit_missing_file` | 1 | `str(e) == f"{p}: file not found"` |
| `test_discovers_toml_in_cwd` | 1 | `tapesift.toml` with `[vlm]` `max_batch = 4` gives `load_config().vlm.max_batch == 4` |
| `test_flags_override_file` | 1 | `tmp_path / "t.toml"` sets `profile = "gpu"` and `out_dir = "a"`. Flags `Profile.CPU` and `Path("b")` win, and `out_dir == Path("b")` stays unresolved. With no flags, the file holds: `out_dir == tmp_path / "a"` |
| `test_config_is_frozen` | 1 | `cfg.asr.model = "tiny"` raises pydantic `ValidationError` |
| `test_model_pins[<pin>]` | 4 | small, tiny, smolvlm2-256m and bge-small-en-v1.5: the exact repo and SHA in the pin table; `revision` fullmatches `[0-9a-f]{40}`; no `files` entry matches `(pytorch_model\|\.pt$\|\.pth$\|\.pkl$\|\.pickle$\|\.ckpt$)`; `BACKEND_ID_RE.fullmatch(pin.id)` |
| `test_config_names_match_pins` | 1 | `typing.get_args` of the `AsrConfig.model` annotation `== tuple(ASR_MODELS)`; the same for `VlmConfig` and `VLM_MODELS` |
| `test_profile_moved_to_config` | 1 | `tapesift.cli.doctor.Profile is tapesift.config.Profile` |
| `test_vision_available[<case>]` | 2 | With `importlib.util.find_spec` patched: both found gives True; torch missing gives False |
| `test_vlm_max_batch[<case>]` | 4 | `vlm_max_batch(cfg)`: unset with profile None gives 8; unset with cpu gives 8; unset with server gives `VLM_MAX_BATCH[Profile.SERVER]` (8); `max_batch = 16` with cpu gives 16 |
| `test_file_path_resolves_against_config_folder` | 1 | `tmp_path / "conf" / "t.toml"` with `out_dir = "idx"`: `load_config(that path).out_dir == tmp_path / "conf" / "idx"` |
| `test_absolute_file_path_is_kept` | 1 | `out_dir = "<tmp_path>/abs"` in the same file gives exactly that path |
| `test_flag_and_default_stay_cwd_relative` | 1 | With `monkeypatch.chdir(tmp_path)` and the conf file above: `load_config(p, out_dir=Path("o")).out_dir == Path("o")`; with an empty file in `conf/`, `out_dir == Path("tapesift_index")` |
| `test_every_path_field_is_listed` | 1 | Walk `Config.model_fields` recursively into nested `_Section` models; the set of key paths whose annotation is `Path` (or `Path \| None`) equals `set(_PATH_KEYS)` |

`tests/unit/test_hub.py`: 6 tests. `huggingface_hub.snapshot_download` is monkeypatched with a recorder that writes the requested files into `tmp_path`. No network.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_cached_snapshot_needs_no_network` | 1 | Step 1 returns a complete dir: exactly one call, with `local_files_only=True`, `revision=pin.revision`, `allow_patterns=list(pin.files)` |
| `test_miss_downloads_with_allow_list_and_timeout` | 1 | Step 1 raises `LocalEntryNotFoundError`. The second call has `local_files_only=False`, `etag_timeout=10.0` and the same revision and allow-list; its dir is returned |
| `test_partial_cache_downloads` | 1 | Step 1's dir lacks one file, so a second call is made |
| `test_missing_file_after_download_is_model_load_error` | 1 | The message ends `missing tokenizer.json` |
| `test_hub_error_is_model_load_error[<exc>]` | 2 | `OSError("offline")` and `RuntimeError("boom")` in step 2 become `ModelLoadError`, whose message starts `cannot fetch BAAI/bge-small-en-v1.5@5c38ec7c405e:` |

`tests/unit/test_doctor.py` (2 tests added; the existing 31 are untouched):
- `test_vision_extra_reported`: `packages={"av": "19.0.1", "transformers": "5.20.2", "torch": "2.14.1"}` gives `report.vision == "transformers 5.20.2, torch 2.14.1"`, and no note contains `tapesift[vision]`.
- `test_vision_extra_missing_is_a_note`: `packages={"av": "19.0.1"}` gives `report.vision is None`. The notes contain the exact note, and `render` contains `vision       not installed (index skips captions)`.

### Smoke tests (`tests/smoke/test_record_boundaries.py`): 8 tests
These use real `probe` and `PyAVDecoder` on fixtures, with fakes for every model.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_fake_vad_matches_fixture_labels[<fixture>]` | 5 | First chunk of each fixture. **speech.mp4**: 2 spans, within 0.02 s of `(0.00, 2.82)` and `(3.20, 6.60)`. **silence.mp4**, **music.m4a**, **av_mismatch.mp4**, **clean.mp4**: `[]` |
| `test_whisper_overshoot_needs_clamp` | 1 | speech.mp4 through `FakeASR(overshoot_s=0.5)`: the second utterance ends at about 7.10, past `duration_s` 7.0. An `AssetRecord` from the raw utterances raises `ValueError` |
| `test_whisper_overshoot_clamped_record_is_valid` | 1 | The same utterances through `clamp_utterance(u, chunk.start_s, min(chunk end, asset.duration_s))` build a valid `AssetRecord`, and the last `end_s <= 7.0` |
| `test_av_mismatch_utterance_clamped_to_duration` | 1 | `probe(av_mismatch.mp4).duration_s == 3.0`. A Whisper-like `Utterance(2.5, 3.04, ..., words=(2.5, 2.9), (2.9, 3.04))` in an `AssetRecord` raises `ValueError`. Clamped to `[0.0, 3.0]`, the record is valid, with end 3.0 and last word `(2.9, 3.0)`. This is the messy-data row "Transcript past the end of video" |

Total new tests: 50 + 36 + 6 + 2 + 32 + 8 = **134**. None is marked `model` or `gpu`.

### Model pins and THIRD_PARTY.md
Rows added under Models:
```
| Systran/faster-whisper-small | 536b0662742c02347bc0e980a01041f333bce120 | ASR, every profile in v0.1 (CTranslate2) | MIT |
| Systran/faster-whisper-tiny | d90ca5fe260221311c53c58e660288d3deb8d356 | ASR for fast CI runs (CTranslate2) | MIT |
| HuggingFaceTB/SmolVLM2-256M-Video-Instruct | 067788b187b95ebe7b2e040b3e4299e342e5b8fd | Frame captions, vision extra (safetensors) | Apache-2.0 |
| BAAI/bge-small-en-v1.5 (onnx/model.onnx and tokenizer.json only) | 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a | Text embeddings for search (ONNX) | MIT |
| Silero VAD v6 (silero_vad_v6.onnx, bundled in faster-whisper) | faster-whisper 1.2.1 | Voice activity detection | MIT |
```
Rows added under Python libraries:
```
| faster-whisper | ASR; brings CTranslate2 (MIT) | MIT |
| onnxruntime | Silero VAD and the text embedder | MIT |
| tokenizers | Text embedder tokenization | Apache-2.0 |
| huggingface-hub | Fetches pinned model files (tapesift.hub) | Apache-2.0 |
| lancedb | Search store; brings pyarrow (Apache-2.0) | Apache-2.0 |
| pydantic | Config validation | MIT |
| transformers | VLM captions, in-process; pinned ==5.20.2 (vision extra) | Apache-2.0 |
| torch | VLM runtime (vision extra) | BSD-3-Clause; PyPI expression: Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT |
| pillow | Image backend for the SmolVLM processor (vision extra) | MIT-CMU |
```

### Dependencies (`pyproject.toml`, `uv.lock`)
All steps can run now (every card is decided). `uv add` is an `ask` rule in `.claude/settings.json`.
1. `uv add "faster-whisper>=1.2.1" "lancedb>=0.40.0" "pydantic>=2.14.1" "tokenizers>=0.23.3" "onnxruntime>=1.31.0" "huggingface-hub>=2.2.0"`, then `uv add --dev "jsonschema>=4.26.0"`.
2. Add these by hand, before step 3, so the lock resolves CPU torch on Linux:
   ```toml
   # Dev and CI only: Linux resolves CPU torch from PyTorch's index (no CUDA wheels).
   # Not in the published wheel's metadata; end users choose with uv's --torch-backend.
   [[tool.uv.index]]
   name = "pytorch-cpu"
   url = "https://download.pytorch.org/whl/cpu"
   explicit = true

   [tool.uv.sources]
   torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]
   ```
3. `uv add --optional vision "transformers==5.20.2" "torch>=2.14.1" "pillow>=13.0.0"`. No num2words (card 7).
4. Under `[tool.pytest.ini_options]`:
   - add `pythonpath = ["."]`;
   - append this to `markers`: `"model: loads real pinned model weights; runs only in the CI models job (owner Q4, 2026-10-19), never on the laptop (ADR 0008). The Silero VAD bundled in faster-whisper is package data and needs no marker (owner Q5)."`

**What end users and E9's README get.** End users are unaffected by step 2, as the planner verified above. The README (E9) must say:
- `uvx tapesift ...` indexes speech only and warns once that captions are off;
- captions need `uvx --from "tapesift[vision]" tapesift ...`, or `uv tool install "tapesift[vision]"`;
- on Linux without an NVIDIA GPU, add `--torch-backend cpu` to skip about 4 GB of CUDA wheels (Q1 measurement);
- the floors from card 10.

### docs/spec.md edits
1. **Interfaces block.** Replace the lines from `class ASR(Protocol):` through the `Store.search` line (115-127) with:
```python
class VAD(Protocol):  # tapesift.audio.types
    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]: ...  # container clock

class ASR(Protocol):  # tapesift.audio.types
    @property
    def id(self) -> str: ...  # "<backend>:<model>@<revision>", recorded in provenance
    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]: ...  # one list per chunk; the stage clamps

class VLM(Protocol):  # tapesift.vision.types
    @property
    def id(self) -> str: ...
    def caption(self, frames: Sequence[Frame], prompt_id: str) -> list[Caption]: ...  # one caption per frame, same t_s

class Embedder(Protocol):  # tapesift.vision.types; image embeddings arrive with S3
    @property
    def id(self) -> str: ...
    @property
    def dim(self) -> int: ...
    def embed_text(self, texts: Sequence[str], *, kind: Literal["query", "passage"]) -> NDArray[np.float32]: ...  # unit rows

class Store(Protocol):  # tapesift.store.types
    def upsert(self, record: AssetRecord) -> None: ...
    def delete(self, asset_id: str) -> None: ...
    def search(self, query: str, k: int = 10, *, modality: Modality | None = None, asset_id: str | None = None) -> list[Hit]: ...
```
2. **Extras table (184).** The `(none)` row becomes `| (none) | PyAV decode, faster-whisper, Silero VAD, PySceneDetect, LanceDB, ONNX text embedder, typer CLI | Must install on any laptop in under 2 minutes |`. Insert directly after it: ``| `vision` | transformers VLM backend (transformers, torch, pillow) for captions | torch adds about 5 GB on Linux with CUDA wheels (owner, 2026-10-19) |``.
3. **After the extras table** (before `**Model serving`), insert this paragraph: ``**Captions need `vision`.** Without it, `tapesift index` indexes speech only: it logs one warning (`captions off: install "tapesift[vision]"`), `tapesift doctor` says `not installed (index skips captions)`, and `provenance.vlm` is null. On Linux without an NVIDIA GPU, add uv's `--torch-backend cpu` to `uvx` or `uv tool install` to skip the CUDA wheels.``
4. **Line 198 and line 206:** card 10's exact edits.
5. **Line 204.** `Only safetensors; \`trust_remote_code\` stays off by default.` becomes `Weights are safetensors, CTranslate2 or ONNX, never pickle; \`trust_remote_code\` stays off (owner, 2026-10-19).`
6. **Line 537.** `- Weights pinned by revision, safetensors only, \`trust_remote_code\` off.` becomes `- Weights pinned by full commit SHA; safetensors, CTranslate2 or ONNX, never pickle; \`trust_remote_code\` off.`
7. **Line 217.** `tapesift index PATH... [--profile]` becomes `tapesift index PATH... [--config FILE] [--profile]` (card 4; E7 still owns the `--workers` edit).
8. **Line 218.** `tapesift search "query" [--k 10]` becomes `tapesift search "query" [--config FILE] [--k 10]`, and `Ranked moments with timestamps, source, confidence` becomes `Ranked moments with timestamps, source and a relevance score; \`--json\` prints {"query", "hits"}` (card 3).
9. **Line 269.** `"id": "sha256:9f2c..."` becomes `"id": "tsid1:9f2c..."` (ADR 0012's default).
10. **Line 271.** `"lang": "en"}` becomes `"lang": "eng"}` (card 5). Line 273's utterance `"lang": "en"` is unchanged.
11. **Toml block (231-262).** Replace it with:
```toml
# v0.1 accepts exactly these keys (src/tapesift/config.py); any other key is an error.
# Found as ./tapesift.toml, or passed with --config FILE.
# Later items add theirs: shot_threshold, dedupe_hamming, max_frames_per_shot and
# strategy "shots+dedupe" (C3, v0.2); vlm.endpoint and backend "openai" (C6, v0.2); [safety] (Y1-Y3).
profile = "gpu"               # "cpu", "gpu" or "server"; unset: tapesift doctor picks
out_dir = "./tapesift_index"  # relative to this file's folder; --out and the default: the current directory

[sampling]
strategy = "fixed"            # the only v0.1 value
fixed_fps = 1.0

[asr]
backend = "faster-whisper"
model = "small"               # "small" or "tiny"; revisions pinned in config.py
compute_type = "int8"
vad_min_speech_ratio = 0.05   # below this, skip ASR for the file
batch_seconds = 600
# audio_track = 1             # index into the file's audio tracks; unset: the default track

[vlm]
backend = "auto"              # "auto" (transformers if tapesift[vision] is installed), "transformers" or "none"
model = "smolvlm2-256m"
# max_batch = 8              # unset: per profile (8 on every profile in v0.1)
prompt = "caption_v1"

[store]
backend = "lancedb"
```

## Acceptance
The baseline is main at 989f5c1: `451 passed, 2 deselected`, `51 files already formatted`. If #21 merges first, the baseline is `515` and `53`, and the second number in each cell applies. The builder states which one in the PR.

| Command | Expected |
| --- | --- |
| `uv run pytest tests/unit/test_records.py -q` | `50 passed` |
| `uv run pytest tests/unit/test_config.py -q` | `36 passed` |
| `uv run pytest tests/unit/test_hub.py -q` | `6 passed` |
| `uv run pytest tests/unit/test_doctor.py -q` | `33 passed` |
| `uv run pytest tests/contract -q` | `32 passed` |
| `uv run pytest tests/smoke/test_record_boundaries.py -q` | `8 passed` |
| `uv run pytest -q -m "not gpu and not model"` | `585 passed, 2 deselected` (or `649 passed, 2 deselected`), with no `failed`, `error`, `skipped` or `xfailed` |
| `make test` | the same line as the row above |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff format --check .` | `71 files already formatted` (or `73`) |
| `uv run ruff check .` | `All checks passed!` |
| `uv lock --check` | exit 0 |
| `grep -c '^name = "nvidia' uv.lock` | `0` |
| `grep -c '^name = "triton"' uv.lock` | `0` |
| `grep -c 'version = "2.14.1+cpu"' uv.lock` | `1` |
| `grep -c '^vision = \[' pyproject.toml` | `1` |
| Command A8 below | `pyproject.toml:0` and `uv.lock:0` |
| `grep -c '^- Interfaces (any lane' AGENTS.md` | `1` |
| `grep -c 'src/tapesift/hub.py' AGENTS.md` | `2` |
| `grep -c 'not gpu and not model' Makefile` | `1` |
| `uv run tapesift doctor` | exit 0 or 3, and a line beginning `vision       transformers ` (CI syncs `--all-extras`) |
| `grep -c 'def embed_images' docs/spec.md` | `0` |
| `grep -c 'never pickle' docs/spec.md` | `2` |
| `grep -c 'safetensors only' docs/spec.md` | `0` |
| `grep -c '^strategy = "fixed" ' docs/spec.md` | `1` |
| `grep -c '"lang": "eng"}' docs/spec.md` | `1` |
| `grep -c '"id": "tsid1:9f2c' docs/spec.md` | `1` |
| `grep -c 'Captions need `vision`' docs/spec.md` | `1` |
| `grep -c 'macOS 14+ on Apple Silicon' docs/spec.md` | `1` |
| `grep -c '\[--config FILE\]' docs/spec.md` | `2` |
| `grep -c '^class Profile' src/tapesift/cli/doctor.py` | `0` |
| `git diff --numstat main -- CHANGELOG.md` | `1	0	CHANGELOG.md` |
| Commands A1-A7 below | as noted on each line |
| `git diff --name-only main...HEAD` | exactly the 29 paths listed below |
| `make check` | exits 0 |

Commands with pipes or quotes, kept out of the table:
```bash
# A1: R6 import guard; prints []
uv run python -c "import sys, tapesift.config, tapesift.hub, tapesift.schema.records, tapesift.audio.types, tapesift.vision.types, tapesift.store.types; print(sorted({'torch','transformers','ctranslate2','faster_whisper','lancedb','pyarrow','onnxruntime','tokenizers','huggingface_hub','av'} & set(sys.modules)))"
# A2: dependency specifiers; prints 10
grep -c -E '"(faster-whisper>=1\.2\.1|lancedb>=0\.40\.0|pydantic>=2\.14\.1|tokenizers>=0\.23\.3|onnxruntime>=1\.31\.0|huggingface-hub>=2\.2\.0|transformers==5\.20\.2|torch>=2\.14\.1|pillow>=13\.0\.0|jsonschema>=4\.26\.0)"' pyproject.toml
# A3: the model marker; prints 1
uv run pytest --markers | grep -c '^@pytest.mark.model:'
# A4 and A5: THIRD_PARTY rows; print 9 and 5
grep -c -E '^\| (faster-whisper|onnxruntime|tokenizers|huggingface-hub|lancedb|pydantic|transformers|torch|pillow) \|' THIRD_PARTY.md
grep -c -E '^\| (Systran|HuggingFaceTB|BAAI|Silero)' THIRD_PARTY.md
# A6: the new Store.search line in docs/spec.md; prints 1
grep -c -F 'asset_id: str | None = None) -> list[Hit]' docs/spec.md
# A7: the published wheel names no index, and torch is optional; prints 0 then 1
uv build --wheel -o /tmp/m1-dist >/dev/null && unzip -p /tmp/m1-dist/tapesift-*.whl '*/METADATA' | grep -c -i pytorch; \
unzip -p /tmp/m1-dist/tapesift-*.whl '*/METADATA' | grep -c -F "Requires-Dist: torch>=2.14.1 ; extra == 'vision'"
# A8: no num2words or docopt anywhere (card 7); prints pyproject.toml:0 and uv.lock:0
grep -c -i -E 'num2words|docopt' pyproject.toml uv.lock
```
`git diff --name-only main...HEAD` prints exactly:
```text
AGENTS.md
CHANGELOG.md
Makefile
THIRD_PARTY.md
docs/spec.md
pyproject.toml
src/tapesift/audio/__init__.py
src/tapesift/audio/types.py
src/tapesift/cli/doctor.py
src/tapesift/config.py
src/tapesift/hub.py
src/tapesift/schema/__init__.py
src/tapesift/schema/records.py
src/tapesift/store/__init__.py
src/tapesift/store/types.py
src/tapesift/vision/__init__.py
src/tapesift/vision/types.py
tests/contract/test_asr.py
tests/contract/test_embedder.py
tests/contract/test_store.py
tests/contract/test_vad.py
tests/contract/test_vlm.py
tests/fakes.py
tests/smoke/test_record_boundaries.py
tests/unit/test_config.py
tests/unit/test_doctor.py
tests/unit/test_hub.py
tests/unit/test_records.py
uv.lock
```

The PR's Numbers section reports the CI `uv sync --locked --all-extras` step time and the venv size on ubuntu-latest and macos-latest, cold and warm, next to main's. On Linux, that's the effect of the CPU torch source.

## Out of scope
- Every implementation:
  - E3: `transcribe_asset`, `SileroVAD`, `FasterWhisperASR`, phantoms, `eval/wer.py`, seam handling (#13);
  - E4: `caption_asset`, `TransformersVLM`, prompts, the caption `conf` derivation;
  - E5: `to_json`, `asset-1.0.schema.json`, rounding;
  - E6: `OnnxEmbedder` (including bge's query prefix), `LanceStore`, `tapesift search`, wiring `--config`;
  - E7: the runner, `tapesift index`, `--config`, the failed markers and summary, the R9 log lines, the out-dir layout beyond `store/` and `failed/`, whether `asset.path` is stored as given or absolute, and whether a non-media file (`.DS_Store`) alone makes the exit code 1.
- The CI `models` job (E3). Removing `--workers` from spec 217 (E7, Q10 B). The publish and install-test workflows (E8). README text (E9; required content is under Dependencies).
- An `asr.audio_track` that is out of range for one file (E3: fall back with a warning, or a `StageError`).
- A `Shot` record (C3); image embeddings (S3); per-profile models (v0.2); `tapesift models pull` (v0.2); `vlm.endpoint` and `openai` (C6); `[safety]` keys (Y1-Y3); `tapesift report` (S4, which reads the failed markers).
- Recording the embedder id in the store (E6).
- `tapesift.example.toml` and the generated config reference (L3).

## Risks
- **The PyTorch CPU index is a second package source.** It is scoped to `torch` only (`explicit = true`), only on Linux, and hashes are pinned in `uv.lock`. If download.pytorch.org is unreachable, CI's `uv sync` fails. That is loud, not silent. If the owner prefers no second index, the alternative is CUDA torch in CI, at about 5 GB per Linux job.
- **macOS CI still installs torch** (`--all-extras`; 1.1 GB venv per Q1). If the warm sync step goes over 3 minutes, stop and raise a card (for example, CI syncs without `vision` and runs E4's `model` job only on Linux).
- **The num2words shim (card 7) depends on a private transformers detail**: the module global `num2words` in `transformers.models.smolvlm.processing_smolvlm`.
  - transformers is pinned `==5.20.2`.
  - If an upgrade removes or renames the global, E4's `hasattr` guard raises `ModelLoadError` loudly. It never fails silently.
  - If the processor starts calling `num2words` on the image path, the stub raises `RuntimeError` and that asset fails (R5).
  - **Fallback:** option A. Add `num2words>=0.5.14` (LGPL-2.1; it brings the sdist-only `docopt` 0.6.2, MIT) to `vision`, drop the shim, and add its THIRD_PARTY row. That's a card (licensing).
- **Xet storage.** huggingface-hub 2.2.0 depends on `hf-xet`, which may download from Xet storage hosts rather than huggingface.co. E3's `models` job records the hosts contacted. If they differ, doctor's `NETWORK_CALLS` line is updated by card (Y3).
- **Pickle in pinned repos.** `BAAI/bge-small-en-v1.5` contains `pytorch_model.bin`. `fetch_pin`'s allow-list is the only fetch path, so reviewers must reject any other `snapshot_download`, `hf_hub_download` or sentence-transformers call.
- **FakeVAD is a heuristic.** Its thresholds are pinned on today's fixtures (CV 0.902 vs at most 0.314). A regenerated fixture that moves those numbers fails `test_fake_vad_matches_fixture_labels` loudly. Fix the fake, never the expectation without a card.
- **Record strictness.** With the clamp in place, a record `ValueError` is a bug, and R5 fails one asset. E3's WARNING over 0.5 s keeps large clamps visible.
- **CLI start-up time.** `cli/doctor.py` now imports `tapesift.config`, so `tapesift --version` loads pydantic. If it slows noticeably, report the number.
- **`pythonpath = ["."]`** makes `tests` and `scripts` importable as namespace packages. No top-level module shadows a stdlib or dependency name today.
- **Merge order with #21.** Only CHANGELOG.md overlaps; keep both lines at rebase. Counts are given for both orders.
- **`filterwarnings = error`.** An import-time `DeprecationWarning` from pydantic or huggingface-hub (imported by `test_hub.py`) fails the suite. Fix the call; never add a filter without a card.

## T1 calls (list them in the PR)
1. `Store.search(query, k=10, *, modality=None, asset_id=None)`: the keyword-only `asset_id` implements the approved `--asset` flag (spec 218). `Store.delete(asset_id)` is added so a changed file leaves no stale rows (finding 14). Both are additive to an internal Protocol.
2. `VAD` Protocol and the `vad` parameter of `transcribe_asset` (finding 6), so E3's stage is fake-testable. `SileroVAD` runs on the laptop (Q5).
3. `ASR.transcribe` keeps `Sequence`; streaming is a stage rule (R8). See "Where this revision disagrees".
4. A CPU torch source for Linux dev and CI (finding 2). It was verified with metadata-only `uv lock`, and the published metadata is unchanged.
5. `tapesift.hub.fetch_pin` is the one model-fetch path (finding 12). It is cache-first, uses an allow-list and timeouts, and wraps errors as `ModelLoadError`.
6. Doctor gains a `vision` field, line and note (finding 3). This is additive to `doctor --json`.
6a. `vlm_max_batch(cfg)` and `VLM_MAX_BATCH` live in `config.py`, next to the defaults they resolve (card 4 decision).
7. `Profile` moves to `config.py`, and `doctor.py` imports it.
8. Records check their invariants in `__post_init__`; `clamp_utterance` is the shared stage-side fix (finding 4).
9. `Modality` and `Hit` live in `schema/records.py`; `ConfigError`, `ModelLoadError` and `vision_available` live in `config.py`.
10. Tests import `tests.fakes` through `pythonpath = ["."]`. Fakes record `calls` for spies. FakeASR is silent on tones (finding 14).
11. The embedder implementation is `vision/embed.py` (spec layout), owned by E6. The store lives at `cfg.out_dir / "store"`.
12. No profile-specific defaults in v0.1 (one model set, owner Q3). If E4's CPU seconds per frame puts the 10-minute talk over 30 minutes, E4 raises the cpu `fixed_fps` card.
