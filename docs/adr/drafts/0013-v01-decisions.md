# 0013. v0.1 owner decisions: vision extra, lean dependencies, pinned models, talk check, PyPI after the public flip, M1 interface cards

Date: 2026-10-20   Status: proposed (draft in docs/adr/drafts/; move to docs/adr/ and mark accepted when merged)   Tier: T2 and T3 (per row)

## Context
v0.1 ("works on your laptop") runs from Oct 19 to Nov 1. Before code could start, the owner had to answer three sets of cards:

- **Q1 to Q11**: the v0.1 planning cards. They are in the v0.1 planning doc (section 4), which is not in the repo. The rows below carry the answers.
- **Seven #21 cards** in [docs/specs/21-safe-opener.md](../../specs/21-safe-opener.md). Approved 2026-10-19 with every recommended option. Shipped in PR #34 (merged).
- **Ten M1 cards** in [docs/specs/25-m1-interfaces.md](../../specs/25-m1-interfaces.md). The spec is committed on local main at 2c6dc88 and is not pushed yet. Decided 2026-10-20. Cards 1 to 7 are T3. They went through two council seats (one opus, one sonnet) and one rebuttal round. Cards 8 to 10 are T2 and the owner decided them directly.

Q1 needed a measurement, so it was timed on GitHub Actions with an empty cache. Run: https://github.com/jahnavi-yelamanchi/tapesift/actions/runs/39347647667

| OS | lean install | full install (lean plus transformers and torch) | lean venv | full venv |
| --- | --- | --- | --- | --- |
| ubuntu-latest | 4 s | 33 s | 778 MB | 6.1 GB |
| macos-latest | 3 s | 10 s | 479 MB | 1.1 GB |

Both operating systems are far under the 120 s bar. Most of the Linux full venv is CUDA (about 4 GB of nvidia and triton wheels). One run per OS, so there is no variance estimate.

Experiment writeup: branch `exp/q1-install-timing`, file `docs/experiments/2026-10-19-q1-install-timing.md`. The experiment branch is kept; not merged. The writeup recommended option A (torch in the base) on the time criterion alone. The owner chose B. The reason recorded in the log: the time bar passes, but the Linux install is about 8 times larger, and speech-only users should not pay for CUDA wheels.

## Options
Each card had options A to C in its source. The rows below name the option chosen. The rejected options are in the source text.

## Decision

### Owner v0.1 decisions (Q1 to Q11)

| ID | Tier | Choice | Why | Revisit if |
| --- | --- | --- | --- | --- |
| Q1 | T2 | B. Captions (transformers and torch) go in a `tapesift[vision]` extra. The base install does speech and text search. Without the extra, `index` skips captions with a visible warning, and `doctor` shows a line. | The time bar passes on both OS. Size decides: the Linux full venv is 6.1 GB against 0.8 GB for lean. Speech-only users should not pay for CUDA. | Users need captions in the base install, or the extra confuses the quickstart (check in E9 and X1). Moving torch out of the base later would be a breaking change. |
| Q2 | T2 | A. Lean dependency set: faster-whisper (its Silero VAD is bundled), lancedb, pydantic, av, numpy, onnxruntime, tokenizers, typer. No torch in the base. The text embedder is about 40 lines on onnxruntime and tokenizers. Dev group: jsonschema. The VLM set moves to the extra under Q1. | Every package is MIT or Apache-2.0. The spec rule is to own about 50 lines rather than add a dependency. | The embedder cannot run the pinned model, or a licence problem appears. |
| Q3 | T2 | A. Pin upstream repos by full commit SHA: Systran/faster-whisper-small (ASR), HuggingFaceTB/SmolVLM2-256M-Video-Instruct (VLM, Apache-2.0), BAAI/bge-small-en-v1.5 `onnx/model.onnx` (embedder, MIT). The rule becomes "safetensors, CTranslate2 or ONNX; never pickle; `trust_remote_code` off". | faster-whisper models are CTranslate2 `model.bin`, which is neither safetensors nor pickle. The pickle ban is the real security line. An upstream pin avoids a mirror job. | An upstream repo is deleted or relicensed, or the 256M VLM fails the X1 visual queries (then use the 500M model). |
| Q4 | T2 | A. A `model` pytest marker. `make check` deselects it. A Linux-only `models` CI job runs `pytest -m model` on PRs that touch audio, vision, store, pipeline or runner, and nightly. It is advisory until it has been green 3 times. macOS runs real models only in E8's tag install test. Modal runs X1 and the GPU tests. | Keeps the laptop on fakes (ADR 0008). Keeps macOS minutes low. | The job takes more than 15 min with a warm cache. |
| Q5 | T2 | A. Local tests may run the Silero VAD bundled in the faster-whisper wheel. | The file arrives with the dependency. No download step. The fast local check is worth it. | The owner reads ADR 0008 as covering any inference on the laptop. |
| Q6 | T2, licensing | B. A CC BY 4.0 talk with slides from Wikimedia Commons. The owner picks the URL and writes 5 queries (3 spoken, 2 on screen) in `evals/v0.1-talk.toml`, by about Oct 28. Posts credit the license. X1 runs on Modal and commits `docs/verification/v0.1-talk.json`. | Slides give visual queries. The license sits on each file page. No personal media goes into git. | No 9 to 11 min CC BY talk with slides is found. Then A: a public-domain US government talk. |
| Q7 | T2 | A. The exit reads "indexes on a laptop-class CPU". The check runs in a Modal CPU container sized like a laptop with the `cpu` profile (the plan proposed 4 vCPU, 16 GB). The demo GIF is recorded with vhs in that container from a committed script. | Keeps ADR 0008 intact. | The owner wants a literal laptop number for the launch clip. |
| Q8 | T2 | A. WER at most 0.20 on `speech.mp4`, after a normalizer in `src/tapesift/eval/wer.py` (lowercase, no punctuation, `%` becomes "percent", integers 0 to 100 become words). The #13 seam check must meet the same bound. | The clip has 15 words, so one error is 6.7%. A 0.10 bound would be flaky with int8 quantization. | Three runs in a row with 0 errors. Then tighten to 0.134 by card. |
| Q9 | T3 | A. Flip the repo public on or before Oct 31. Publish `v0.1.0rc1` to TestPyPI, then `v0.1.0` to PyPI, with trusted publishing. The owner adds the pending publishers and a protected `pypi` environment. | The spec requires v0.1.0 on PyPI. The name `tapesift` returned 404 on PyPI and TestPyPI on 2026-10-19. ADR 0004 ties the flip to the first public release. | A reason to stay private until Dec 6. Then B: a CI-built wheel, and spec 333 is amended. Note: a PyPI upload makes the source public for good. |
| Q10 | T2 | B. Ship `--max-hours` and `--dry-run` (files, hours, skip and resume counts; no cost line). `--workers` moves to S1 (v0.3), and spec 217 is updated. | With in-process models, `--workers` means N copies of the models in RAM. A cost line needs the C7 throughput data (v0.2). | A v0.1 user with many cores and small models asks for `--workers`. |
| Q11 | T2, process | A. Wave 2 (up to 6 parallel builders, E3 to E8) starts once M1 merges. It does not wait for Oct 26. | The owner's answer: "up to 6 parallel builders once M1 merges". | Spec drift turns up in the M1 or #21 review. |

### #21 safe opener cards (approved 2026-10-19, all recommended)

| ID | Tier | Choice | Why | Revisit if |
| --- | --- | --- | --- | --- |
| 21-1 | T2 | A. Refused inputs reuse `UNREADABLE`, with the details `not a regular file: <kind>` and `container format not allowed or header invalid`. No enum change. | No schema change. The existing row already covers "cannot open". | The runner report must tell policy refusals from broken files. Then B, at the next schema bump. |
| 21-2 | T2 | A. Nine allowed containers: mov, matroska, avi, mpegts, wav, mp3, aac, flac, ogg. | The owner's list. Each one has a test. | The owner's library has `.mpg`, `.vob` or `.aiff` files. Then add them (B). |
| 21-3 | T2 | A. `OPEN_TIMEOUT_S = 30.0` applies to every stage. Non-regular files are refused without blocking. A read stuck in the kernel stays unbounded until the runner wall-clock limit (#36). | Small. Closes the FIFO hang. | A stalled network mount shows up in real use before #36 lands. |
| 21-4 | T2 | A. Symlinks are followed. The target must be a regular file. | Media libraries use links (git-annex, Plex, Jellyfin). A link to a FIFO or device is refused. | A multi-user or server mode, such as `tapesift serve` taking paths from remote clients. |
| 21-5 | T2 | A. Rewrite the two probe tests. Remove `PROBE_TIMEOUT_S`. | Cheap. | Nothing likely. |
| 21-6 | T2 | A. Open through a checked descriptor: `os.open` with `O_NONBLOCK`, `fstat`, blocking set again, then `av.open("fd:")` with `protocol_whitelist="fd"`. The file extension no longer decides the format. | No path reaches FFmpeg, so no nested file reads and no playlist fetches. | A real file type that tapesift must support is detectable only by its extension. |
| 21-7 | T2 | A. Public `UnsafeInputError(OSError)` in `tapesift.media.safe_open`, not re-exported from `tapesift.media`. | Probe's and decode's existing `except (FFmpegError, OSError)` clauses catch it unchanged. | The owner wants no Python type names in user-visible details. |

### M1 interface cards (decided 2026-10-20)

| ID | Tier | Choice | Why | Revisit if |
| --- | --- | --- | --- | --- |
| M1-1 | T3 | C. A failed file gets no JSON and no store rows. E7 writes `out_dir/failed/<asset_id>.json` (stage, exception type, error, attempts, tapesift version). A rerun retries while attempts are under 2 for the same tapesift version. A success deletes the marker. `StageError` still degrades. No schema change. | `UNREADABLE` and `PARTIAL_DECODE` keep their M0 meanings. A new code would need a fixture no media file can give. | Real runs show one stage crashing deterministically and dropping transcripts users want. Then A (a new code), at a schema minor bump. |
| M1-2 | T3 | A. In v0.1, `"shots": []`. Every caption has `"shot": null`. `caption.conf` may be null. `utterances[].conf` stays required. | True in every mode and backend. Consumers handle null. | C3 decides `fixed` mode should emit time-window shots. |
| M1-3 | T3 | A. `search --json` is `{"query": ..., "hits": [...]}`. Each hit has `asset_id`, `path`, `start_s`, `end_s`, `modality` ("speech" or "visual"), `text`, `media_text` (a separate list), `score` (not comparable across queries) and `trust: "untrusted_media"`. | Media text is delimited by structure, not by string tricks. Output is safe by default. | Y1 needs untagged output as a baseline. Its harness can strip the tag instead. |
| M1-4 | T3 | A, with two changes. (a) `vlm.max_batch` is `None` by default, resolved per profile by `config.vlm_max_batch(cfg)`. In v0.1 that is 8 for every profile. (b) A path key written in a config file resolves against that file's folder. `--out` and the default stay relative to the current directory. `index` and `search` take `--config FILE`. Precedence: flag, file, default. | Keeps CPU-safe defaults. A changed default later would count as a behaviour change, so the default is resolved, not fixed. | E4 measures that 8 is much slower than 16 or 32 on the CI runner without a memory problem. Then raise the value by card. |
| M1-5 | T3 | A. Two documented meanings. `asset.audio.lang` is the container tag as written (`"eng"`, `"und"`, or free text). `utterances[].lang` is the ISO 639-1 code the ASR detected. The JSON Schema says both, and passes unknown tags through. | Lossless. Matches M0. | A consumer has to join the two. Then add a normalized field (a minor bump). |
| M1-6 | T3 | A. `provenance` backend ids are `"<backend>:<model>@<revision>"`. The revision is 40 lowercase hex or the literal `unpinned`. `BACKEND_ID_RE` enforces it. | One string form now and in v0.2. Greppable. | C6 finds servers report a revision that must be recorded separately. |
| M1-7 | T3, licensing | Guarded shim, not num2words. `huggingface-hub` goes in the base. `pillow` goes in `vision`. `transformers==5.20.2` is pinned exactly. E4's loader checks that `processing_smolvlm` has a `num2words` attribute. If it is missing, `ModelLoadError` is raised. Otherwise the loader sets a stub that raises if called. The video path is not used in v0.1. | No LGPL-2.1 package ships. The stub never runs on the frame path. | A licence review rejects the shim, or a transformers upgrade breaks the guard. Then fall back to num2words (LGPL-2.1, in the vision extra), as the spec's Risks section describes. |
| M1-8 | T2 | A. `Embedder` has `id`, `dim` and `embed_text(texts, *, kind)`, where `kind` is `"query"` or `"passage"` and is required. Texts over the limit are truncated, never rejected. No `embed_images` until S3. | The query and passage prefixes are explicit at every call. | The pinned embedder becomes symmetric. Then `kind` is a no-op, which is harmless. |
| M1-9 | T2 | A. AGENTS.md lanes: Core adds `schema/`, `config.py` and `hub.py`. Shared interface files are editable only through an approved interface spec. This PR makes the edit. | M0 and M1 files are used by every lane. | The owner prefers per-spec grants. |
| M1-10 | T2 | A. The platform floor: Linux x86_64 with glibc 2.28+, or Apple Silicon on macOS 14+. Intel Macs are not supported. Spec lines 198 and 206 are edited. | onnxruntime 1.31, lancedb 0.40 and torch 2.14 ship no older or Intel macOS wheels. | A buyer needs Intel Macs. Then Docker (S5). |

## Consequences
- Base install stays small (about 0.8 GB on Linux, 0.5 GB on macOS). Captions need `tapesift[vision]`.
- Real models are pinned by commit. Real-model checks run in one Linux CI job, and on Modal.
- Nothing in v0.1 can emit shots, a `--workers` flag, or a per-stage failure code. Those are v0.2 and v0.3 changes.
- Publishing to PyPI makes the source public for good. The public flip is the point of no return for Q9.
- Not decided here: option A-prime from the Q1 writeup (torch in the base but pinned to the CPU index). It would be a separate T2 card.

## Revisit if
Any row's "Revisit if" fires. Each row names its trigger.
