# Video + Audio Engine: Build Plan

Oct 13, 2026 · @jahnavi

## The plan on one page

You are building **tapesift** (working name, free on PyPI as of today): an open-source, self-hosted engine that turns hours of video and audio into searchable, timestamped data at the lowest cost per hour. Then you post-train a small model per domain so it beats big APIs on that domain. The headline numbers are **video-hours processed per GPU-hour** and **dollars per video-hour**.

Three phases, each shipped in public:

1. **Engine (Oct 14 to Dec 6).** v0.1 to v0.4 on PyPI. Anyone runs it with `uvx tapesift` on a laptop CPU or an NVIDIA GPU. Proves systems skill: decode, sampling, batching, cost per hour.
2. **Evals, post-training, safety (Dec 7 to Jan 3).** Eval harness, an SFT then RLVR adapter for one domain, and a media prompt-injection benchmark. Proves research engineering.
3. **Self-training loop and v1.0 (Jan 4 to Jan 31).** The model labels its own footage, checks itself, retrains, and you publish the curve and the stop rule. Proves closed-loop improvement and gives the business pitch real numbers.

How you work: you are the tech lead. Claude Code subagents, dispatched in parallel from one lead session, write most of the code (ADR 0009). You write specs, make decisions, review diffs, and hand-write four pieces on purpose so you can defend them in interviews. Your adoption goal is to move from step 1-2 to step 3 by mid-December, with explicit gates in the Orchestration section.

The sentence this project earns you, with real numbers filled in: *"I built an open video and audio engine that processes X video-hours per GPU-hour at $Y per hour, RL-tuned a small model that beats \[API\] on \[domain\] at a fraction of the cost, and published a benchmark for prompt injection hidden in media."*

How to use this doc: read top to bottom once. After that, live in three sections: **Feature backlog** (what to build next), **Decisions** (what you must decide, with my default and a deadline), and **Orchestration** (how to run the agents). When an agent hits a question this doc doesn't answer, that is a decision: write a short ADR and add it to the log.

## Product spec

v1.0 takes a folder of video or audio, produces a timestamped record of what was said and shown, and answers "find the moment where X is said or shown" from a CLI, a Python API, or an HTTP API, all on the user's own machine.

**Users, in priority order**

| User | What they have | What they need from tapesift | How they'll judge it |
| --- | --- | --- | --- |
| ML engineer or data person at a company with video | Hundreds to thousands of hours, privacy rules | Self-host, batch index, search, export | Cost per hour, install pain, does it crash on their files |
| AI lab data team (video gen, world models, robotics) | Raw footage to curate for training | Shot splits, dedupe, captions, transcripts, filters | Throughput, caption quality, JSONL output |
| Solo developer or researcher | A laptop, some recordings | `uvx tapesift` and a search box | Works in 5 minutes on a CPU |
| You, later, as the business | Domain pilots | Domain packs (tuned adapters + extraction schema) | Accuracy vs big API, $ per hour |

**v1.0 scope (what "complete" means, not a demo)**

- Ingest any common container (mp4, mov, mkv, webm, avi, m4a, mp3, wav), single files, folders, or a manifest file.
- Survives messy files: one bad file never kills a batch; every failure lands in a report with a reason.
- Resumable: rerunning skips finished work by content hash. Killing the process loses at most the in-flight batch.
- Speech: voice activity detection, transcription with word timestamps, language ID.
- Vision: shot boundaries, near-duplicate removal, captions per kept frame or shot, visual embeddings.
- Fused timeline per asset: shots, utterances, captions, all on one PTS-based clock in seconds.
- Search: text query over speech, visual captions, and image embeddings, ranked, with timestamps and a confidence.
- Outputs: JSON per asset, JSONL for the corpus, SRT/VTT transcripts, CSV of segments.
- Runs on CPU (slow, small models), consumer NVIDIA GPU, and datacenter GPU, picked automatically by `tapesift doctor`.
- `tapesift bench` reports the headline numbers on the user's own hardware.
- Evals, a domain adapter, and safety reports ship as documented, reproducible commands.

**Non-goals (written down so agents and contributors don't drift)**

- No face recognition, person identification, or tracking of named individuals. Ever. This goes in the README.
- No hosted service in v1.0. The managed version is a business decision for later.
- No video generation or editing.
- No training of base models. Only post-training of small open models.
- No real-time streaming in v1.0. Batch first; streaming is a v2 question.
- No Windows-native support in v1.0. WSL2 is best effort.
- English only in v1.0 (ADR 0010). Other languages are transcribed best effort, with the detected language recorded per utterance, but nothing is evaluated or tuned for them.

## Positioning

tapesift's parts (Whisper, open VLMs, vLLM, a vector DB) are free and widely used, so the parts aren't the edge. The edge is the combination: the cheapest way to index video that can't leave your network, one command on any machine, and a pipeline that gets cheaper and more accurate on your footage over time.

**The technical idea to lead with: listen first, look only when needed.** Transcribing audio is cheap; having a VLM look at frames is usually where most of the bill goes. So tapesift transcribes first, finds where the picture changes, and sends the VLM only frames where something new happens that the speech doesn't already explain. The self-training loop then learns, per domain, how sparse sampling can get before accuracy drops.

- Number to publish: VLM calls per video-hour and $ per video-hour, at equal golden-search accuracy.
- The v0.2 stage breakdown must confirm vision is the expensive stage. If it isn't, revisit the idea.
- In week 1, read prior work on adaptive frame selection so the claim says exactly what's new.

**What else is out there** (checked Oct 13, 2026)

| Tool | What it is | How it stands out | Where tapesift differs |
| --- | --- | --- | --- |
| [Twelve Labs](https://usagepricing.com/blueprint/twelve-labs) | Hosted API with its own video models | Model quality; about $2.50 per hour of video to index, plus search and storage fees | Its public offer is a cloud API (also on AWS Bedrock); tapesift runs on your hardware |
| [VideoDB](https://cdn.jsdelivr.net/npm/videodb@0.2.7/Readme.md) | Hosted video database: upload, index speech and scenes, search, stream clips | Developer experience; results stream as clips | Hosted only |
| [Mixpeek](https://mixpeek.com/blog/twelve-labs-alternative) | Multimodal search, self-hosted or cloud, bring your own models | Runs in your VPC; self-hosted license about $2K to $8K a month | tapesift is open source and free to self-host |
| [NVIDIA VSS](https://docs.nvidia.com/vss/3.0.0/overview/3.0.0/) | Reference architectures for video agents, search and summarization | Full NVIDIA stack, enterprise analytics | tapesift is one command, not a blueprint to assemble |
| [NeMo Curator video](https://docs.nvidia.com/nemo/curator/latest/get-started/video.html) | Open-source pipeline that splits, embeds and captions video for training data | Lab-scale curation | GPU only, roughly 16 to 38 GB VRAM, a dataset tool rather than search; tapesift runs from a laptop up |
| [Edit Mind](https://selfhostyourself.com/services/edit-mind), [SentrySearch](https://feedbagel.com/post/sentrysearch-open-source-semantic-video-search-tool-using-gemini-embedding-2) | Open-source local video search projects | Simple and local | Hobby-grade; Edit Mind says it isn't production-ready and includes face recognition |

The open spot: open source, production-grade, runs on anything from a laptop to an H100, and publishes its cost per hour. None of the tools above is all four.

**Who needs it**

- Teams whose footage can't leave their network: litigation support, insurance claims, media archives, corporate training libraries.
- Products that need to "watch" video: meeting and screen-recording tools, agent companies, robotics teams sorting demo footage.
- Video-gen and world-model labs, as a cheap first pass before heavy curation.
- Platforms that could ship it as a template or integration: inference clouds, vector databases, video infrastructure companies.

**How to show it's quick**

- Quick to start: time from `uvx tapesift` to the first search result on a laptop, recorded in one take.
- Quick to process: video-hours per GPU-hour across GPUs, in the README.
- Cheap: $ per video-hour beside Twelve Labs' $2.50 list price, with golden-search quality next to it so the comparison is fair.
- The launch clip: a naive 1 fps pipeline and tapesift on the same GPU and the same 10 hours, split screen, timer running.
- For post-training: one chart of accuracy vs cost per hour for the base model, a big API and the tuned model.

**Say these out loud:** no face recognition, ever, and the published media prompt-injection benchmark. Both matter to legal and enterprise buyers.

## Architecture

One process, five layers: CLI, pipeline, stages, backends, store. Every backend sits behind a Python Protocol, so it can be swapped for another or replaced by a fake in tests.

&#91;embedded content: tapesift pipeline · 2 lanes, 12 stages\]

The one highlighted box is the sampler: it decides how many frames reach the VLM, which is most of the cost per hour.

**Interfaces.** Finalize these in Phase 0 as ADR 0002. Interfaces are the decisions you review hardest, because every lane builds against them.

```python
def probe(path: Path, *, full_hash: bool = False) -> AssetInfo: ...  # tapesift.media.probe; PyAV, one implementation

class Decoder(Protocol):
    def iter_frames(self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink) -> Iterator[Frame]: ...  # Frame.t_s comes from PTS
    def iter_audio(self, asset: AssetInfo, sample_rate: int = 16_000, *, track: int | None = None, chunk_s: float = 600.0, warn: WarningSink) -> Iterator[AudioChunk]: ...

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

**Repo layout**

```text
tapesift/
  AGENTS.md  CLAUDE.md  README.md  CHANGELOG.md  LICENSE  THIRD_PARTY.md  SECURITY.md
  pyproject.toml  uv.lock  Makefile  tapesift.example.toml
  src/tapesift/
    cli/        typer commands: doctor, index, search, show, export, bench, serve, eval, train
    config.py   pydantic models, the only home of defaults
    schema/     output JSON Schema and record types
    media/      probe, decode backends (pyav, torchcodec), sampling
    kernels/    Triton: perceptual hash and Hamming distance
    audio/      VAD, ASR backends
    vision/     VLM backends (transformers, openai-compatible), embeddings
    pipeline/   stages, fusion, bounded-queue scheduler
    runner/     SQLite job store, resume, report
    store/      LanceDB store, hybrid ranking
    serve/      FastAPI app
    eval/       suites, metrics (tIoU, WER), bench
    safety/     untrusted-media tagging, PII redaction, injection flag
    train/      SFT, GRPO, self-training loop (train extra)
  tests/        unit/ contract/ smoke/ gpu/ fixtures/
  evals/        suite manifests, results, CHANGELOG.md
  bench/        scripts and published results
  scripts/      make_fixtures.py, release helpers
  docs/         spec.md, adr/, site sources
  devlog/       drafts/ and published posts
  .claude/      settings.json, agents/, skills/, workflows/
```

## Install and distribution

Ship a Python package on PyPI, installed with uv, plus two Docker images. No npx: this is a Python project, and a Node wrapper would add a second toolchain for no user benefit.

**What a stranger types**

```bash
# zero-install trial
uvx tapesift doctor
uvx tapesift index ./my_videos
uvx tapesift search "where do they talk about pricing"

# permanent install
uv tool install tapesift
uv tool install "tapesift[gpu,serve]"

# GPU server
docker run --gpus all -v $PWD/videos:/data ghcr.io/<you>/tapesift:cuda index /data
```

**Package extras**

| Extra | Adds | Why it's optional |
| --- | --- | --- |
| (none) | PyAV decode, faster-whisper, Silero VAD, PySceneDetect, LanceDB, ONNX text embedder, typer CLI | Must install on any laptop in under 2 minutes |
| `vision` | transformers VLM backend (transformers, torch, pillow) for captions | torch adds about 5 GB on Linux with CUDA wheels (owner, 2026-10-19) |
| `gpu` | torchcodec CUDA decode (NVDEC) | Needs NVIDIA driver and system FFmpeg |
| `serve` | FastAPI + uvicorn HTTP API | Not every user wants a server |
| `train` | TRL, PEFT, datasets | Heavy; only for post-training |
| `dev` | ruff, pyright, pytest, hypothesis, pre-commit | Contributors only |

**Captions need `vision`.** Without it, `tapesift index` indexes speech only: it logs one warning (`captions off: install "tapesift[vision]"`), `tapesift doctor` says `not installed (index skips captions)`, and `provenance.vlm` is null. On Linux without an NVIDIA GPU, add uv's `--torch-backend cpu` to `uvx` or `uv tool install` to skip the CUDA wheels.

**Model serving (decision 0002): users never set up vLLM.** On a laptop or Mac, small models run inside tapesift. On an NVIDIA GPU, tapesift starts vLLM itself with `uvx vllm serve <model>`, which runs it in its own isolated environment, so vLLM's pinned torch never clashes with tapesift's. tapesift waits for the health check, sends batched requests, and stops the server when the run ends. Teams that already run vLLM or SGLang set `vlm.endpoint` and tapesift uses theirs. The `cuda` Docker image ships with vLLM inside. The tradeoff is a large one-time download on the first GPU run, which `tapesift models pull` can do ahead of time.

**Decode default.** PyAV wheels bundle FFmpeg, so CPU decode works with zero system setup. NVDEC through torchcodec is the `gpu` extra, because it needs FFmpeg installed on the system. `doctor` tells the user which one they have.

**Hardware tiers** (picked by `tapesift doctor`, overridable with `--profile`)

| Profile | Hardware | ASR | VLM | Decode | Expect |
| --- | --- | --- | --- | --- | --- |
| `cpu` | A Linux x86\_64 laptop (glibc 2.28+) or an Apple Silicon Mac on macOS 14+ | faster-whisper small, int8 | tiny open VLM (SmolVLM2-class) | PyAV | Works, slow; good for 1-10 hours |
| `gpu` | Consumer NVIDIA, 8 GB+ | faster-whisper large-v3-turbo, int8 | 2B-class open VLM | NVDEC | Real use on hundreds of hours |
| `server` | L4, L40S, A100, H100 | same, batched across files | 2B-8B VLM on vLLM that tapesift starts itself | NVDEC | The benchmark numbers |

Model picks are defaults to verify in week 1: license (prefer Apache-2.0 or MIT, record each in `THIRD_PARTY.md`), size, and video support in vLLM.

**Models and offline installs.** Weights download on first use into the Hugging Face cache, pinned to a revision hash in code. `tapesift models pull --profile gpu` pre-downloads for air-gapped servers. Weights are safetensors, CTranslate2 or ONNX, never pickle; `trust_remote_code` stays off (owner, 2026-10-19).

**Platforms.** Linux x86\_64 is first-class and tested in CI. macOS arm64 runs the `cpu` profile and is tested in CI on the smoke suite. Floors: glibc 2.28+ on Linux, macOS 14+ on Apple Silicon; Intel Macs are not supported (onnxruntime, lancedb and torch ship no macOS x86_64 wheels). Windows is WSL2, best effort.

**Release mechanics.** Tag `vX.Y.Z` on main, GitHub Actions builds with `uv build`, publishes to PyPI with trusted publishing (no API token stored), builds and pushes both images to GHCR, and drafts release notes from the changelog.

## CLI, config and output schema

The CLI is the product's front door, so its shape is decided before code. Every command has `--json` for machine output, and exit codes mean the same thing everywhere: **0** all good, **1** finished but some files failed (see report), **2** bad config or arguments, **3** environment problem (missing GPU, missing model).

| Command | Does | Release |
| --- | --- | --- |
| `tapesift doctor` | Reports Python, PyAV/FFmpeg, CUDA, GPU name, VRAM, NVDEC, free disk, picks a profile | v0.1 |
| `tapesift index PATH... [--config FILE] [--profile] [--out DIR] [--workers N] [--max-hours H] [--dry-run]` | Indexes files or folders; resumes by content hash; `--dry-run` prints the plan and estimated cost | v0.1 |
| `tapesift search "query" [--config FILE] [--k 10] [--modality speech\|visual\|any] [--asset ID]` | Ranked moments with timestamps, source and a relevance score; `--json` prints {"query", "hits"} | v0.1 |
| `tapesift bench [--suite small\|full] [--gpu-cost-per-hour USD]` | Headline numbers on this machine, writes `bench.json` | v0.2 |
| `tapesift models pull\|list` | Pre-downloads pinned weights and, on NVIDIA, the vLLM runtime | v0.2 |
| `tapesift show ASSET` | Terminal timeline: shots, speech, captions | v0.3 |
| `tapesift export --format jsonl\|srt\|vtt\|csv` | Writes outputs for the whole index or one asset | v0.3 |
| `tapesift serve [--host] [--port]` | HTTP API: `POST /index`, `GET /jobs/{id}`, `GET /search`, `GET /assets/{id}` | v0.3 |
| `tapesift mcp` | MCP server with search, show and clip tools for agents | v0.3 |
| `tapesift report` | Failures, quarantined files, warnings from the last run | v0.3 |
| `tapesift eval SUITE` | Runs a frozen eval suite, writes results with git SHA | v0.5 |
| `tapesift train sft\|grpo CONFIG` | Post-training entry points (`train` extra) | v0.6 |

**Config.** One `tapesift.toml`, validated by pydantic at startup with errors that name the bad key. CLI flags override the file; the file overrides profile defaults. Every value has a default, so an empty file is valid.

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

**Output schema (one asset).** Every timestamp is seconds from the container start, computed from PTS, never from frame index divided by fps. Every record carries the model and prompt version that produced it, so evals and retraining can trace any output back.

```json
{
  "schema_version": "1.0",
  "asset": {"id": "tsid1:9f2c...", "path": "talks/keynote.mp4", "duration_s": 3612.4,
            "video": {"codec": "h264", "w": 1920, "h": 1080, "fps_avg": 29.97, "vfr": true, "rotation": 0},
            "audio": {"codec": "aac", "tracks": 1, "lang": "eng"}, "license": null},
  "shots": [{"id": 0, "start_s": 0.0, "end_s": 12.48, "kept_frames_s": [0.5, 6.1]}],
  "utterances": [{"start_s": 3.2, "end_s": 7.9, "text": "...", "lang": "en", "conf": 0.91,
                  "words": [{"w": "pricing", "start_s": 5.1, "end_s": 5.6}]}],
  "captions": [{"t_s": 6.1, "shot": 0, "text": "...", "conf": 0.74, "media_text": ["on-screen words, tagged untrusted"]}],
  "warnings": [{"code": "VFR_DETECTED", "detail": "timestamps taken from PTS"}],
  "provenance": {"tapesift": "0.3.0", "asr": "faster-whisper:large-v3-turbo@<rev>", "vlm": "<model>@<rev>", "prompt": "caption_v1"}
}
```

Schema changes follow semver: adding a field is a minor bump, renaming or removing one is a major bump with a migration note. Agents must stop and ask before touching this schema.

## Messy multimodal data

Real footage breaks clean pipelines, and handling it well is the clearest senior signal in this project. Every case below gets a synthetic fixture (generated by `scripts/make_fixtures.py` with FFmpeg's test sources, a few seconds each, so they're license-free and run in CI) and a test that asserts the handling.

The rule behind all of it: **one bad file degrades, never crashes.** A failure becomes a warning code on the asset or a line in `tapesift report`, and the batch keeps going.

| Case | What breaks if you ignore it | Detect | Handle | Warning code |
| --- | --- | --- | --- | --- |
| Variable frame rate (phone video) | Timestamps drift by seconds over an hour | avg vs nominal frame rate, PTS gaps | All times from PTS | `VFR_DETECTED` |
| Rotation metadata | VLM sees sideways frames, captions degrade | display-matrix side data | Rotate at decode | `ROTATED` |
| Non-zero stream start | Speech and shots misalign | stream `start_time` | Normalize to container start | `START_OFFSET` |
| Audio and video lengths differ | Transcript past the end of video | compare stream durations | Clip to shortest, warn | `AV_LENGTH_MISMATCH` |
| No audio track | ASR stage crashes | probe | Skip ASR, mark asset | `NO_AUDIO` |
| Several audio tracks | Wrong track transcribed (e.g. commentary instead of main) | probe | Default track; `asr.audio_track` override | `MULTI_AUDIO` |
| Silence or music only | Whisper invents text ("thanks for watching") | VAD speech ratio | Skip ASR below threshold; drop known phantom phrases | `LOW_SPEECH` |
| Truncated or corrupt file | Decoder throws mid-file | decode errors | Keep partial results, record the gap | `PARTIAL_DECODE` |
| Not a media file or unopenable (e.g. `.srt`, `.DS_Store` in a folder) | One stray file aborts a folder run | probe | Skip with the exact reason | `UNREADABLE` |
| Codec this machine can't decode (ProRes, AV1 without support) | Hard failure | capability check | Fall back to CPU decode or skip with the exact reason | `UNSUPPORTED_CODEC` |
| Interlaced broadcast | Comb artifacts in frames | field order | Deinterlace before sampling | `INTERLACED` |
| Letterbox or pillarbox | Wasted pixels, worse captions | crop detection on sample frames | Crop before VLM | `CROPPED` |
| HDR or 10-bit | Washed-out frames | pixel format | Convert to 8-bit SDR | `HDR_CONVERTED` |
| Very long file (3h+) | Memory blows up | duration | Stream in chunks, never load whole | none |
| Very short clip (under 1s) | Shot detector edge cases | duration | Single-frame path | `SHORT_CLIP` |
| 4K or 8K | Decode cost and VRAM | resolution | Downscale at decode | `DOWNSCALED` |
| Same file twice | Paying twice | content hash | Index once, link both paths | `DUPLICATE` |
| Unicode or spaces in paths | Path bugs on some OSes | none | `pathlib` everywhere; fixtures named `réunion 01.mp4` | none |
| Burned-in text or captions | VLM reads it as instructions (see Safety) | OCR flag in caption output | Store as `media_text`, tagged untrusted | `MEDIA_TEXT` |

Two things agents get wrong here unless told: they compute time as `frame_index / fps`, and they wrap a whole batch in one try/except. Both are banned in `AGENTS.md`.

## Feature backlog

Each item becomes one GitHub issue, one branch, one worktree, one PR. "Done when" is the acceptance test the agent must show passing before you review. Lanes are defined in Orchestration. Items marked **(you)** are hand-written by you on purpose; agents may only review them.

### Phase 0: Setup (Oct 14 to 18)

Note: this is the setup week. ADR 0001 and `docs/status.md` also say "Phase 0 (engine)" for the first of the three build phases (Oct 14 to Dec 6). The setup week is the first part of it.

Exit: a stranger clones the repo, runs `uv sync && make check`, and it passes; two agents have worked in parallel worktrees without a conflict. Verified 2026-10-18 on a fresh clone with gh access; re-run as a true stranger at the public flip.

- [x] **P0.1** GitHub repo, Apache-2.0, README stub with the non-goals. Done when: the repo exists and the name is final (decision D1). Private until launch (ADR 0004 amendment); the owner sets the flip date (open question). **(you)**
- [x] **P0.2** `uv init --package`, `src/tapesift/`, Python 3.12+ (ADR 0011), typer CLI with `--version`. Done when: `uvx --from . tapesift --version` prints. *Lane: Core*
- [x] **P0.3** ruff (lint + format), pyright strict on `src/`, pytest, pre-commit, `make check`. Done when: `make check` runs all of it in under 3 minutes. *Lane: Core*
- [x] **P0.4** GitHub Actions on every PR (Linux + macOS), required to merge; branch protection on `main`. Done when: a PR with a lint error cannot merge. *Lane: Core*
- [x] **P0.5** `scripts/make_fixtures.py` builds every messy-data fixture, under 5 MB total, committed. Done when: one fixture per row of the messy-data table. *Lane: Media*
- [x] **P0.6** `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.worktreeinclude`, ADR template, issue and PR templates (content in Orchestration). Done when: the Claude Code subagents (ADR 0009) follow them on a test task. **(you write AGENTS.md; agents fill the rest)**
- [x] **P0.7** `tapesift doctor`. Done when: correct output on your laptop and on a rented GPU box, tested with mocked environments. *Lane: Core*

### v0.1 "Works on your laptop" (Oct 19 to Nov 1)

Exit: CI indexes all fixtures on CPU; a 10-minute talk indexes on your laptop; 5 hand-checked queries return the right moment; `uvx tapesift` works from PyPI on a fresh Linux and Mac machine. Ship v0.1.0.

- [ ] **E1** Probe and asset ID. Done when: every fixture probes with the right warning codes. Asset ID = sha256 of size + first 8 MB + last 8 MB (fast on huge files; full-hash option for paranoid users, see ADR). *Lane: Media*
- [ ] **E2** CPU decode (PyAV) with fixed-fps sampling, PTS timestamps, rotation, downscale to 768 px long side. Done when: VFR fixture timestamps match PTS within 1 frame. *Lane: Media*
- [ ] **E3** Audio: 16 kHz mono extraction, VAD, faster-whisper with word timestamps, phantom-phrase filter. Done when: silence fixture yields zero utterances; speech fixture WER under a set threshold. *Lane: Core*
- [ ] **E4** VLM captions, transformers backend, prompt `caption_v1`, batched. Done when: captions for all kept frames, prompt version recorded. *Lane: Core*
- [ ] **E5** Fuse into schema 1.0 JSON; JSON Schema file plus a validation test. Done when: every output validates. *Lane: Core*
- [ ] **E6** LanceDB store, text embeddings, `search`. Done when: golden queries on fixtures return expected IDs. *Lane: Core*
- [ ] **E7** Runner v0: per-file isolation, hash-based resume, progress bar, failure report. Done when: corrupt fixture fails alone and a rerun skips finished files. *Lane: Core*
- [ ] **E8** Packaging: TestPyPI then PyPI release workflow with trusted publishing. Done when: fresh-VM install test passes in CI. *Lane: Core*
- [ ] **E9** README quickstart, 30-second demo GIF. *Lane: Docs*

### v0.2 "Cost" (Nov 2 to 15)

Exit: a published before/after table on one L4 with a per-stage breakdown, whatever the number turns out to be. Ship v0.2.0 and post part 1 of the cost write-up.

- [ ] **C1** Per-stage timers and `--trace out.json` in Chrome trace format, viewable in Perfetto. *Lane: Core*
- [ ] **C2** Baseline benchmark at 1 fps fixed sampling, written up before any optimization. **(you run and write it)**
- [ ] **C3** Shot detection (PySceneDetect) + perceptual-hash dedupe + `max_frames_per_shot`. Done when: frames sent to the VLM drop, golden-query recall holds. *Lane: Media*
- [ ] **C3b** Triton kernel: batched perceptual hash and Hamming distance on GPU, so frames stay on the GPU after NVDEC. Done when: matches the CPU reference bit for bit and beats it on 1080p batches. **(you)**
- [ ] **C4** NVDEC decode via torchcodec, auto-picked by `doctor`. *Lane: Media*
- [ ] **C5** Batched ASR across files, length-sorted to cut padding. *Lane: Core*
- [ ] **C6** Managed vLLM: on NVIDIA GPUs tapesift starts \`uvx vllm serve\` in its own environment, health-checks it, sends batched requests with bounded in-flight and timeouts, and stops it at the end; \`vlm.endpoint\` still accepts your own vLLM or SGLang server. Done when: \`tapesift index\` works on a fresh GPU box with no extra setup. *Lane: Core*
- [ ] **C7** `tapesift bench`: video-hours per GPU-hour, $ per video-hour, GPU utilization, peak VRAM, per-stage share. *Lane: Eval*
- [ ] **C8** Cost-quality frontier: frames processed vs golden-query recall across sampling settings. *Lane: Eval*

### v0.3 "Scale" (Nov 16 to 29)

Exit: 50 hours indexed on one L4 without you touching it; `kill -9` mid-run and resume loses at most one batch; memory stays flat across 100 files.

- [ ] **S1** Pipelined runner: decode, sample, ASR and VLM as stages with bounded queues so the GPU never waits. Done when: GPU utilization reported and higher than v0.2. **(you write the scheduler core; agents wire stages to it)**
- [ ] **S2** SQLite job store (jobs, files, stage status), resume at shot granularity. *Lane: Core*
- [ ] **S3** Visual embeddings (SigLIP-class) and hybrid ranking (keyword + vector, fused scores). *Lane: Core*
- [ ] **S4** `serve` HTTP API with OpenAPI docs, `report` command. *Lane: Core*
- [ ] **S5** Docker images `cpu` and `cuda` (vLLM bundled) on GHCR. *Lane: Media*
- [ ] **S6** `show` and `export` (jsonl, srt, vtt, csv). *Lane: Docs*
- [ ] **S7** Soak test: 100 files, concurrent, memory bounded, no leaked processes. *Lane: Eval*
- [ ] **S8** `tapesift mcp`: an MCP server with search, show and clip tools, so Claude or any agent can search someone's local footage. Done when: Claude Code finds a moment in the demo corpus through it, and every result carries the untrusted-media tag. *Lane: Core*

### v0.4 "Ship" (Nov 30 to Dec 6)

Exit: launch posted; at least 3 people outside your circle installed it (issues, stars or DMs as evidence).

- [ ] **L1** 100-hour demo corpus of public-domain and CC-BY video (NASA, Internet Archive public domain, Blender open movies), license stored per asset. *Lane: Media*
- [ ] **L2** Benchmarks on L4, L40S, H100, rented by the hour; table and chart in README. **(you run them)**
- [ ] **L3** Docs site: quickstart, config reference generated from the pydantic models, architecture, FAQ. *Lane: Docs*
- [ ] **L4** Write-up "What it costs to understand an hour of video" and launch. **(you)**
- [ ] **L5** CONTRIBUTING.md and 10 `good first issue` tickets. *Lane: Docs*

### v0.5 to v0.7: Evals, post-training, safety (Dec 7 to Jan 3)

Detail lives in the Evals, Post-training and Safety sections.

- [ ] **V1** `tapesift eval` harness: frozen suites with content hashes, results JSONL stamped with git SHA. *Lane: Eval*
- [ ] **V2** ASR suite: WER on short, long-form and accented English speech, reported by group. *Lane: Eval*
- [ ] **V3** Moment-retrieval suite and the tIoU metric. **(you write the metric)**
- [ ] **V4** Golden set: 50 queries you label on the demo corpus. **(you)**
- [ ] **V5** Big-API comparison on 200 samples, cost logged. *Lane: Eval*
- [ ] **T1** Domain pick (decision D8), data card, splits by video. **(you)**
- [ ] **T2** SFT LoRA baseline with TRL. *Lane: Train*
- [ ] **T3** Reward functions with property-based tests. **(you)**
- [ ] **T4** GRPO run with reward-hacking monitors. *Lane: Train*
- [ ] **T5** Encode each video once per GRPO group and share it across rollouts; measure rollout throughput before and after. *Lane: Train*
- [ ] **T6** Adapter on Hugging Face Hub with a model card. *Lane: Docs*
- [ ] **Y1 to Y5** Safety work items (see Safety). *Lane: Eval*

### v0.8 to v1.0: Self-training and release (Jan 4 to 31)

- [ ] **R1** `tapesift train selfloop`: generate, filter, audit, train, evaluate per round. *Lane: Train*
- [ ] **R2** Run 3 to 4 rounds; publish the curve and the stop rule. **(you)**
- [ ] **R3** Self-tuned sampling settings per domain (sparsest setting that holds accuracy). *Lane: Eval*
- [ ] **R4** Domain pack format: adapter + extraction schema + prompts + eval suite, installable by name. *Lane: Core*
- [ ] **R5** v1.0: public API and schema frozen, migration notes, SECURITY.md, CITATION.cff. *Lane: Docs*
- [ ] **R6** Technical report (arXiv-ready) covering cost, post-training, self-training and the safety benchmark. **(you)**

## Evals

Every number you post comes from a command anyone can rerun. Two kinds of evals: **systems** (is it fast and cheap) and **quality** (is it right). Neither counts without the other.

**Systems metrics** (from `tapesift bench`)

| Metric | Definition |
| --- | --- |
| Throughput | video-hours processed / GPU-hours of wall clock |
| Cost | GPU price per hour / throughput, in $ per video-hour (user passes the price) |
| Time to first result | seconds from start to the first searchable segment |
| GPU utilization | mean utilization sampled through NVML during the run |
| Peak memory | peak VRAM and peak process RSS |
| Stage share | % of wall clock per stage (decode, sample, ASR, VLM, embed, store) |
| Failure rate | failures per 1,000 files on the messy suite |

**Quality suites** (from `tapesift eval`)

| Suite | Data | Metric | Note |
| --- | --- | --- | --- |
| ASR short | LibriSpeech test-clean and test-other subset | WER | CC BY 4.0 |
| ASR long-form | Earnings-call recordings (Earnings-21) | WER, timestamp drift | Check license in week 5 |
| ASR fairness | Common Voice English subset with accent and gender labels | WER per group, max gap | CC0 |
| Moment retrieval | QVHighlights validation subset | R@1 at tIoU 0.5 and 0.7 | Annotations non-commercial: eval only, never train |
| Golden search | 50 queries you write on the demo corpus | hit within 5 s, in top 5 | Yours |
| Caption grounding | 200 frames, checked by you | hallucination rate (claims not visible in frame) | Yours |
| Big-API baseline | the same 200 samples through a frontier API | accuracy and $ | Cost logged per run |

**tIoU, the metric you hand-write.** Let p\_s and p\_e be the predicted start and end in seconds, and g\_s and g\_e the true start and end.

```latex
\mathrm{tIoU} = \frac{\max(0,\ \min(p_e, g_e) - \max(p_s, g_s))}{\max(p_e, g_e) - \min(p_s, g_s)}
```

Intuition: how much of the combined span the two intervals share; 1 is a perfect match, 0 is no overlap. Example: predicted 10 to 20 s, true 15 to 25 s. Overlap is 5 s, combined span is 15 s, so tIoU = 0.33, which misses at the 0.5 threshold. Edge cases your tests must cover: zero-length spans, touching spans, prediction containing the truth.

**Rules that make evals trustworthy**

- Freeze each suite as a manifest of file hashes. Changing a suite means a new version name.
- Split by video, never by clip, so clips from one video can't leak between train and test.
- Stamp every result row with git SHA, config hash, model revisions, hardware and date.
- Report bootstrap 95% confidence intervals. A difference inside the interval is noise, and you say so in the post.
- A small CPU subset runs nightly in CI; the full suite runs on demand on a GPU.
- A regression past a set threshold blocks the release.
- Keep `evals/CHANGELOG.md`: when a number moves, write why in one line.

**The chart to post first:** the cost-quality frontier. x is $ per video-hour, y is golden-search recall, one point per sampling setting. It answers the buyer's first question and shows you think in tradeoffs.

## Post-training

Start from a small open VLM (2B to 4B), adapt it to one domain in three steps, and ship each step only if it beats the previous one on the frozen eval. Step zero is a prompt-only baseline: if a better prompt closes the gap, training wasn't needed, and saying so is a senior move.

**Stack.** TRL (`SFTTrainer`, `GRPOTrainer`) with PEFT LoRA, pinned. Before T2, confirm the pinned TRL version handles your VLM with video or multi-image input; if not, verl is the fallback. One rented GPU, capped by budget decision D9.

**Data**

- Task format: input = frames from a segment + the transcript excerpt + an instruction; target = JSON in the domain's extraction schema.
- Sources: public labeled data for the domain (T1), your own corrections on the demo corpus, and later user corrections (opt-in only).
- Corrections are the flywheel input. `tapesift correct ASSET` (v0.6) writes `corrections.jsonl`: output ID, field, old value, new value, who, when.
- Splits by video. Near-duplicate clips across splits are removed by perceptual hash.
- A data card ships with every dataset: sources, licenses, counts, known gaps.

**Step 1: SFT.** LoRA on attention and MLP projections, vision encoder frozen at first. Starting points to tune on validation: rank 16, alpha 32, learning rate 1e-4 to 2e-4, 1 to 3 epochs. Compare against base zero-shot and the prompt baseline.

**Step 2: RLVR with GRPO.** Intuition first. For each prompt, sample G answers, score each with reward r\_i, and compute its advantage against the group:

```latex
A_i = \frac{r_i - \mathrm{mean}(r_1, \dots, r_G)}{\mathrm{std}(r_1, \dots, r_G)}
```

Answers better than their siblings get pushed up, worse ones pushed down, with a KL penalty keeping the model near the SFT reference. Example: G = 4 answers with tIoU rewards 0.8, 0.4, 0.4, 0.0. Mean 0.4, so the first answer gets a positive advantage, the last a negative one, the middle two zero.

| Task | Reward | Range | How it gets hacked | Guard |
| --- | --- | --- | --- | --- |
| Moment search | tIoU(predicted, true) | 0 to 1 | Malformed spans | Unparseable output scores 0 |
| Structured extraction | 0.2 x valid JSON + 0.8 x field F1 | 0 to 1 | Empty valid JSON to farm the 0.2 | Validity counts only if at least one field is right |
| Counting | 1 if exact, else 0 | 0 or 1 | Rarely | None needed |
| Transcript correction | input WER minus output WER, clipped at 0 | 0 to 1 | Copying the input | Reward is the improvement, so copying scores 0 |

Monitors on every run: training reward vs held-out metric (if reward rises and held-out doesn't, it's hacking), output length distribution, KL to reference, format-failure rate, and 20 sampled rollouts per eval step that you read yourself. Starting knobs: G = 8, small KL coefficient, capped new tokens.

**Step 2b: the systems contribution (T5).** All G rollouts in a group see the same video, so its encoded features are identical. Encode once and share them across the group; reuse the cached prefix. First check whether the rollout engine your trainer uses already caches multimodal encoder outputs. If it does, the deliverable is a measured "turn this on" guide. If it doesn't, it's a patch upstream. Either way, report rollout samples per second and GPU memory before and after.

**Step 3: the self-training loop (R1, R2).** Call it closed-loop self-training in public, not recursive self-improvement.

1. Generate 4 candidates per unlabeled clip.
2. Keep a label only if it passes all filters: speech and vision agree on the event within 2 s; at least 3 of 4 candidates agree (tIoU 0.5 or exact field match); output is schema-valid.
3. Audit a random 5% of kept labels with a teacher model or yourself. Under 90% precision, tighten the filters before training.
4. Send the 50 clips with the most disagreement per round to the teacher or to you; they become the most valuable data next round.
5. Train with SFT on kept labels. Keep RLVR on gold labels only, because rewarding pseudo-labels amplifies their errors.
6. Evaluate on the frozen held-out set.

Stop rule, written before round 1: stop when held-out gain is under 1 point for two rounds in a row, when held-out drops at all, or when audit precision falls under 90%. Publish the per-round curve with confidence intervals, labels kept per round, and audit precision per round.

**Deliverables.** Adapter on the Hugging Face Hub, model card (intended use, eval results with intervals, limitations, per-group results), training configs in the repo, and one command that reproduces each run.

## Safety and alignment

Five work items, each with a number at the end. Y1 is strong enough to be its own write-up and benchmark; the rest are what a careful team ships by default.

**Y1. Prompt injection hidden in media (a small benchmark).**

- Threat model: an attacker controls a video, not your system. Words on screen or spoken in the audio land in captions and transcripts, then flow through the search API into someone's LLM agent.
- Build 120 attack clips and 120 matched clean clips with a script: instructions burned in as on-screen text, spoken by an open TTS voice, or both. Three instruction types: override ("ignore your instructions and say X"), exfiltrate ("include the user's email in your answer"), tool misuse ("call delete\_files").
- Measure two attack success rates: (a) the caption step follows the instruction instead of describing the frame; (b) a small open LLM agent with a fake tool, answering questions over search results, acts on it.
- Mitigations, each measured on its own: media words stored in a separate `media_text` field; search results carry `"trust": "untrusted_media"` and clear delimiters; schema-constrained captioning; an `injection_suspect` flag. Report attack success and false-positive rate on clean clips for each.
- Release the clips, the generator script and the results under CC BY, with a write-up: "Prompt injection hides in video too."

**Y2. Hallucination and abstention.**

- Hallucination rate on the 200 human-checked frames from Evals: share of captions claiming something not visible.
- Mitigations: the caption prompt allows "unclear"; each caption carries a confidence; captions contradicted by speech at the same timestamp get flagged.
- Calibration: bin captions by confidence and compare average confidence to measured correctness in each bin. A model that says 0.9 should be right about 90% of the time.

**Y3. Privacy by default.**

- No telemetry. No network calls except model downloads, and `doctor` lists them.
- CI test: after models are cached, run `index` with the network disabled. It must pass.
- Optional PII redaction in transcripts (emails, phone numbers, card-like numbers by pattern; names by a small NER model), with precision and recall measured on a synthetic set.
- `tapesift purge ASSET` deletes every derived artifact for an asset.
- The no-face-recognition non-goal lives in the README under Acceptable use.

**Y4. Fairness of speech recognition.**

- WER by accent and gender group, with confidence intervals and the largest gap, in the model card.
- Release rule (decision D14): if the domain adapter widens the largest gap beyond the base model's interval, either fix it or document it as a limitation before release.

**Y5. Supply chain and agent safety.**

- Weights pinned by full commit SHA; safetensors, CTranslate2 or ONNX, never pickle; `trust_remote_code` off.
- `uv.lock` committed; weekly dependency updates (an agent routine from week 4).
- Automated security review on every PR, GitHub secret scanning on, `SECURITY.md` with a contact.
- Agents never hold publish credentials. PyPI and GHCR publish only from CI through trusted publishing.
- Claude Code runs in auto mode with deny rules for secrets and an ask rule for pushes until step 2 is earned (see Orchestration).

Alignment work inside post-training (reward-hacking monitors, the self-training stop rule, audits) is specified in that section; it counts here too when you talk about it.

## Orchestration

You start with 2 agents in week 1, run 4 to 6 by week 3, and by mid-December hand repeatable work to subagents, workflows and scheduled routines. Each step is earned by trust you've measured, not by agent count.

The detailed agent workflow (roles, subagent files, prompts, decision protocol, feature squads) lives in [tapesift Agentic Workflow](https://claude.ai/code/artifact/c7bf6537-34a1-472f-8ce7-e09c0c09c785). Its `AGENTS.md` v2 replaces the v1 below.

**Who does what.** You write briefs, make decisions, review diffs, merge, hand-write the four **(you)** pieces, and post. Agents implement briefs, write tests, run `make check`, open PRs, and review each other's PRs.

### One-time setup (Phase 0, about 2 hours)

```bash
# Optional: herdr keeps the lead session alive across laptop sleeps (ADR 0009)
# curl -fsSL https://herdr.dev/install.sh | sh

# GitHub CLI (agents use it to read issues and open PRs)
gh auth login

# inside the repo
echo ".claude/worktrees/" >> .gitignore
printf ".env\n" > .worktreeinclude   # copies your .env into every Claude worktree
```

Then run `claude` once in the repo to accept workspace trust, and run `/auto-mode-setup` inside it so the auto-mode classifier knows your GitHub account is trusted.

### Files that carry the context

| File | Read by | Holds |
| --- | --- | --- |
| `AGENTS.md` | Every agent, through `CLAUDE.md` | The single source of truth: commands, rules, stop-and-ask list, definition of done |
| `CLAUDE.md` | Claude Code | One line, `@AGENTS.md`, plus Claude-only notes |
| `.claude/settings.json` | Claude Code, committed | Project permission rules |
| `~/.claude/settings.json` | Claude Code, personal | `autoMode.environment` (the classifier ignores this block in project files) |
| `.claude/agents/*.md` | Claude Code | Subagents: `planner`, `spec-critic`, `feature-builder`, `test-writer`, `fixture-maker`, `reviewer`, `test-auditor`, `council`, `scribe` |
| `.claude/skills/*/SKILL.md` | Claude Code | Repo skills: `add-fixture`, `decision-card`, `run-bench`, `ship-feature`, `write-adr` |
| `docs/adr/NNNN-*.md` | Everyone | Decisions with context and tradeoffs |

`AGENTS.md`, version 1 (you write this one yourself; it's the most important file in the repo):

```markdown
# tapesift agent guide

## What this is
Self-hosted engine: video and audio in, timestamped searchable data out.
Spec: docs/spec.md. Decisions: docs/adr/.

## Commands
- Setup: uv sync --all-extras
- Everything: make check   (must pass before you say done)
- Fast loop: uv run pytest tests/unit -x -q
- Smoke on fixtures: uv run pytest tests/smoke -q

## Rules
- Timestamps come from PTS, in seconds. Never frame_index / fps.
- One bad file never fails a batch: catch per file, record a warning code.
- Typed code; pyright strict passes on src/. No print; use the logger.
- Every network or subprocess call has a timeout.
- A bug fix starts with a failing test.

## Stop and ask before
- Adding a dependency.
- Changing CLI commands or flags, config keys, or the output schema.
- Deleting, skipping or loosening a test.
- Touching paths outside the brief.
Write the question, 2-3 options, your recommendation, then wait.

## Done means
make check is green and the PR says: what changed, how you tested it,
numbers before and after if it touches performance, open questions.
```

`.claude/settings.json` for steps 1 and 1.5 (remove the two `ask` rules for push and PR creation when you reach step 2; branch protection still guards `main`):

```json
{
  "permissions": {
    "allow": ["Bash(make check)", "Bash(uv run pytest *)", "Bash(uv run ruff *)", "Bash(uv run pyright *)", "Bash(gh issue view *)", "Bash(gh pr view *)"],
    "ask": ["Bash(git push *)", "Bash(gh pr create *)", "Bash(uv add *)"],
    "deny": ["Read(./.env)", "Read(./.env.*)", "Bash(uv publish *)"]
  }
}
```

### Lead session layout

One lead Claude Code session dispatches subagents in parallel (ADR 0009). herdr is optional: it keeps the lead alive across laptop sleeps and holds the GPU shell.

| Where | Runs | Mode |
| --- | --- | --- |
| Lead session | You talk here; it dispatches `planner`/`spec-critic`, `feature-builder` squads, `reviewer`/`test-auditor`, `council`, `scribe` | Auto mode |
| Builder worktrees | One `feature-builder` per spec, `isolation: worktree`, with its `test-writer` and `fixture-maker` helpers inside the same worktree | Auto mode |
| `claude agents` | Background sessions you started yourself | Agent view |
| GPU | Modal and Vast jobs from `scripts/cloud/`, `bench/`, `evals/` | You approve each run |

### Lanes

Each lane owns paths, so two parallel builders never edit the same directory in the same week. Every lane is built by `feature-builder` subagents; the model per role is a starting guess (ADR 0009).

| Lane | Built by | Owns | Starts |
| --- | --- | --- | --- |
| Core | Claude Code | `src/tapesift/{cli,pipeline,runner,store,audio,vision,serve}/` and their tests | Phase 0 |
| Media | Claude Code | `src/tapesift/media/`, `scripts/make_fixtures.py` | Phase 0 |
| Eval | Claude Code | `src/tapesift/{eval,safety}/`, `bench/`, `evals/` | v0.2 |
| Train | Claude Code | `src/tapesift/train/` | v0.6 |
| Docs | Claude Code, smaller model | `docs/`, `README.md`, `devlog/` | v0.1 |
| Review | `reviewer` + `test-auditor` (both sonnet), in parallel | Nothing; read-only | Phase 0 |

### The brief (issue template)

```markdown
## Goal
One sentence: what exists after this that didn't before.
## Read first
Files, spec section, related ADRs.
## Scope
Paths you may change. Paths you must not touch.
## Done when
Commands that must pass and the numbers they must show.
## Already decided
## Stop and ask if
```

### One task, start to finish

1. Write the issue from the template (10 minutes) and label it `agent-ready`.
2. In the lead session, have a `planner` and `spec-critic` write the spec; approve and commit it; then dispatch a `feature-builder` on it (prompts P1, P2 in docs/workflow.md).
3. Walk away. If the lead surfaces a decision card, answer from the Decisions section, or write a new ADR if it's a real decision.
4. When it opens the PR, the lead runs `reviewer` and `test-auditor` in parallel (P5).
5. Read in this order: PR description, the review, the tests, interface changes, then the implementation. Use the review checklist in Engineering standards.
6. Comment for changes, or squash-merge and remove the worktree.
7. If the PR was bad, ask "what context was missing?" and fix `AGENTS.md`, a skill or the brief template, not just the code. This habit is what step 3 is made of.

### Step 1 to step 3, with gates

| Step | Dates | Agents | What changes for you | Gate to move on |
| --- | --- | --- | --- | --- |
| 1.5 | Oct 14 to 25 | 2 parallel builders, plus their helpers and reviewers | You read every line; you learn the brief and the review | `make check` under 3 min in CI; 10 agent PRs merged; zero merge conflicts |
| 2 | Oct 26 to Nov 22 | 4 to 6 | Auto mode always on; automated review and security review on every PR; push and PR `ask` rules removed; you review diffs, not keystrokes | 70%+ of agent PRs merge without you editing code; CI catches problems before you do |
| 2.5 | Nov 23 to Dec 13 | 6 to 10, plus subagents | Repo skills; `/batch` for wide changes; workflows for audits; agents pick `agent-ready` issues themselves | A week where most PRs came from issues agents filed or picked |
| 3 | Dec 14 on | 10+, some started by Claude or a schedule | Routines run maintenance; agents start and wait on other agents; you supervise outcomes | Maintenance happens without you starting it; you spend more time deciding than reading diffs |

### Step 2.5 and 3 machinery

- **Subagents.** `feature-builder.md` carries `isolation: worktree`; its `test-writer` and `fixture-maker` helpers run inside the builder's worktree (verified Oct 16, 2026). `reviewer`, `test-auditor`, `spec-critic` and `council` are read-only.
- **`/batch`** splits one wide change into 5 to 30 worktree-isolated subagents. Use it for mechanical sweeps: "add warning codes to every stage", "add docstrings to the public API".
- **Dynamic workflows.** Ask "use a workflow to audit every stage under `src/tapesift/` for per-file error isolation, and adversarially verify each finding before reporting it." Watch it with `/workflows`; press `s` to save a good one into `.claude/workflows/` so it becomes a command. If you're on Pro, keep `/config workflowSizeGuideline=small` until you know the token cost.
- **Agent view.** `claude agents` dispatches background sessions and shows which need you.
- **Agents starting agents.** The lead dispatches builders; each builder dispatches its own test-writer (subagents nest up to three layers). Finished subagents resume with SendMessage, so the builder that wrote a PR also fixes its review findings with its context intact.

- **Scheduled work.** Claude Code routines (cloud, on a schedule) for the weekly dependency-update PR and weekly issue triage. A nightly cron on the GPU box for `tapesift bench --suite small` and the eval subset, posting a summary as a GitHub issue.
- **From your phone.** herdr keeps sessions alive when you close the laptop; reattach over SSH. Claude Code remote control works for watching Claude sessions.

### Traps

- Adding agents before `make check` is trustworthy. More agents then means more broken PRs for you to read.
- Two agents owning the same directory. Merge conflicts eat the time you saved.
- Agents quietly choosing dependencies, schemas or defaults. That's what the stop-and-ask list is for.
- Token burn. Docs and devlog lanes use a smaller model; workflows run on a small slice first.
- Your own skills going soft. The four hand-written pieces, and explaining one merged PR out loud in each vlog, keep you interview-ready.

## Engineering standards

One bar for your code and agent code. If a rule matters, it lives in CI or `AGENTS.md`, not in your head.

**Git**

- Trunk-based. `main` is protected: PR, green CI and your approval, then squash-merge.
- Branches: `feat/<id>-<slug>`, `fix/<id>-<slug>`, `exp/<slug>` for experiments that never merge directly.
- Conventional Commits: `feat(asr): batch transcription across files (#23)`.
- PRs under about 400 changed lines, not counting tests and fixtures. Bigger means split it.
- No Claude co-author trailers in commits or PRs (owner's rule, CLAUDE.md). Agent use is disclosed in AGENTS.md, workflow.md and the devlog instead.
- Tags `vX.Y.Z`; `CHANGELOG.md` in Keep a Changelog sections, updated in every user-facing PR.

**CI**

| Job | When | Time budget | Blocks |
| --- | --- | --- | --- |
| Format, lint, type check | Every PR | 1 min | Merge |
| Unit tests, Linux and macOS | Every PR | 2 min | Merge |
| Smoke run on fixtures, CPU | Every PR | 3 min | Merge |
| Offline run (network off after model cache) | Every PR, from v0.3 | 3 min | Merge |
| Automated security review | Every PR | n/a | Advisory, then merge from step 2 |
| AI code review (`reviewer` + `test-auditor` subagents) | Every PR | n/a | Advisory |
| Install test from the built wheel in a clean container | Release tag | 5 min | Release |
| Bench small + eval subset | Nightly on the GPU box | 20 min | Opens an issue on regression |

**Code structure rules**

- Layers: `cli` calls `pipeline`, which calls stages, which call backends. Backends sit behind Python Protocols, so each one can be swapped and faked in tests.
- Fusion, metrics and timestamp math are pure functions. Side effects live only in the runner and the store.
- Pydantic config models are the only place defaults live; the config docs are generated from them.
- Structured logs, one line per event, always with `asset_id` and `stage`; `--log-json` for machines.
- Each stage raises its own exception type carrying a warning code, so the runner can record it without guessing.
- Seeds fixed and recorded in every eval and training run.

**Tests**

- Unit: many, fast, pure functions; property-based tests (hypothesis) for tIoU and timestamp math.
- Contract tests per backend Protocol, run against both the real backend and its fake.
- Smoke end-to-end on fixtures with the tiniest models, on CPU.
- GPU tests marked `@pytest.mark.gpu`, run nightly on the box.
- Snapshot tests check structure and timestamps of outputs, never model-written text, which changes run to run.

**Performance work**: profile first, write the hypothesis in the PR, change one thing, rerun on the same hardware, report the median of 3 runs with the spread. No number, no merge for perf PRs.

**Your review checklist** (paste into the PR template; answer it in your head on every PR):

1. Does it do what the issue asked, and nothing else?
2. Did it change the CLI, config, schema or dependencies? Was that approved?
3. What happens on a bad file, a timeout, empty input, a 3-hour input?
4. Would the tests fail if the code were wrong? Mentally break one line and check.
5. If it claims a speedup, is there a before and after from the same machine?
6. Will you know what this does in 3 months from its names alone?
7. Could you debug it from the logs at 2 a.m.?
8. Is there a simpler version that gets 90% of the value?

## Decisions

Most decisions are cheap to reverse: make those in under 10 minutes with a rule of thumb, write one line in the PR, and move on. Spend real time only on the few that are hard to undo, and write those up as ADRs.

### How to decide

1. **Can it be undone in a day?** If yes, apply a rule of thumb below and move on.
2. **Who breaks if it's wrong?** Users' data and users' scripts matter most; only-you problems matter least.
3. **What would change your mind?** Write it down as the revisit trigger.
4. **What's the cheapest test?** If an experiment answers it in under 2 hours, run it instead of debating.

Hard to undo in this project: the package name, the license, the output schema, CLI command names, config keys, the asset ID scheme, benchmark numbers once posted, and what data you train on. Each gets an ADR.

### Rules of thumb for small calls

These answer most of what agents will ask you.

- Pick the boring, widely used library. The clever one needs a written reason.
- Measure before optimizing. Never take a speedup on faith, including your own.
- Safe defaults, opt-in power: privacy on, telemetry off, aggressive sampling opt-in.
- Fail per file, loudly, with a code. Never silently.
- Prefer a config key over a new code path, and prefer neither.
- When two options are close, pick the one that's easier to delete later.
- Don't add a dependency for something you could own in about 50 lines.
- When an agent offers three options, ask which is easiest to reverse, and start there.
- Name things for what they do for the user, not how they work inside.

### ADR template

```markdown
# NNNN. The decision, stated as a sentence
Date: YYYY-MM-DD   Status: accepted | superseded by NNNN
## Context
What forces this now. Numbers if you have them.
## Options
1. ... pros, cons
2. ...
## Decision
## Consequences
What gets easier, what gets harder, what we can no longer do.
## Revisit if
The observation that would change this.
```

### Open decisions

Each has my default. Accept it by writing the ADR, or overrule it with your reason. Both count as practice.

| ID | Decision | My default | Why | Decide by |
| --- | --- | --- | --- | --- |
| D1 | Project name | `tapesift` (`reelsift` and `framesift` are also free on PyPI today) | "Tape" covers audio and video and sounds like archives, which is who pays | Oct 14, before the repo goes public |
| D2 | Your inner-loop machine | Laptop on the `cpu` profile with tiny models; GPU work on a rented box via `herdr --remote` | Fast feedback locally, real numbers remotely | Oct 14 |
| D3 | License | Apache-2.0 | Patent grant, business-friendly, standard for open-core infrastructure | Oct 14 |
| D4 | Default VLM per profile | Smallest Apache-2.0 model with video support in vLLM that passes the golden queries | License and vLLM support decide it, not leaderboard rank | Oct 25 (E4) |
| D5 | Vector store | LanceDB, embedded | No server to run; swappable behind the store Protocol | Oct 25 (E6) |
| D6 | Asset ID | sha256 of size + first and last 8 MB; full hash opt-in | Fast on 10 GB files; the collision risk is written down | Oct 21 (E1) |
| D7 | Test fixtures | Small files committed, generated by a script | Reproducible, no Git LFS | Oct 18 |
| D8 | First post-training domain | Lectures and talks | Open data exists, answers are checkable, buyers exist (edtech, corporate training libraries) | Dec 5, after buyer conversations |
| D9 | Monthly GPU budget | $100 cap, rented by the hour, instances stopped by script | Keeps experiments honest about cost | Oct 18 |
| D10 | Your weekly hours here | 2 hours each weekday + 4 hours one weekend day | Agents multiply hours you protect, not hours you hope for | Oct 14 |
| D11 | Public from day one | Private until launch (owner, Oct 16; ADR 0004 amendment); owner sets the flip date, open question | Public before the first release; commits are visible from the flip | Oct 16 |
| D12 | Python floor | 3.12 (ADR 0011; was 3.11 in ADR 0005) | PyAV 19 and numpy 2.5 require 3.12; one decoder version under test | Oct 16 |
| D13 | Where training code lives | Same repo, behind the `train` extra | One version, one issue tracker | Dec 7 |
| D14 | Fairness release rule | Block release if the adapter widens the largest WER gap beyond the base model's interval, unless documented | Makes the fairness work binding | Dec 7 |
| D15 | Who reviews whose code | Superseded by ADR 0009: `reviewer` and `test-auditor` (both sonnet) review every PR in parallel | One tool; diversity from lens and model | Decided Oct 16; revisit after ~20 merged PRs |

### Decision log

Newest first. One row per ADR; the ADR file holds the detail.

| # | Date | Decision | Revisit if |
| --- | --- | --- | --- |
| 0011 | Oct 16 | Python 3.12 floor (supersedes 0005) | A target platform pins 3.11 |
| 0010 | Oct 16 | English only in v1.0 | A buyer or pilot needs another language |
| 0009 | Oct 16 | Claude Code subagents only, several per step; Codex dropped | Post-merge bugs not near zero after ~20 PRs |
| 0008 | Oct 16 | Laptop builds code; models, data and training run on Modal, Vast, Colab, HF Hub | Cloud round trips cost hours a week |
| 0007 | Oct 16 | English speech fixture from espeak-ng | A permissive natural English TTS is scriptable |
| 0006 | Oct 16 | Fixtures are small synthetic files, generated and committed | Fixtures pass 5 MB |
| 0005 | Oct 16 | Python 3.11 floor, develop on 3.12 (superseded by 0011) | A key dependency drops 3.11 |
| 0004 | Oct 16 | Name tapesift, Apache-2.0, build in public (repo private for now) | PyPI name taken before E8 |
| 0003 | Oct 13 | Add `tapesift mcp` in v0.3 so agents can search local footage | Nobody uses it by v1.0 |
| 0002 | Oct 13 | tapesift starts and stops vLLM itself on NVIDIA GPUs; users may still point at their own server | Managed startup fails on common setups, or the one-time download blocks first runs |
| 0001 | Oct 13 | Build tapesift in three phases: engine, then evals and post-training, then self-training | Buyer conversations by Dec 15 show no demand and job outreach gets no replies |

## Build in public

One post per merged feature, one per real decision, a Friday numbers thread and a Sunday vlog. An agent drafts; you edit and post. Agents never post for you.

| What | When | Format | Where |
| --- | --- | --- | --- |
| Feature post | Each merged user-facing PR | 2 to 4 lines + a 20-second terminal recording | X; weekly roundup on LinkedIn |
| Decision post | Each ADR | Template below | X |
| Numbers thread | Fridays | What shipped, one number, one failure, next week | X, cross-posted to LinkedIn |
| Talking out loud | Daily, 2 minutes | Voice memo or raw screen recording while reviewing a PR | Raw material only |
| Vlog | Sundays, 8 to 12 minutes | herdr screen + face cam | YouTube, clipped to X |
| Write-ups | v0.2, v0.4, Y1, R2 | Long-form post on your site | Site, Show HN, r/LocalLLaMA, GPU MODE |

**Post templates**

```text
Decision: X over Y for Z.
Why: <one reason, with a number>.
Cost: <what I gave up>.
Revisit if: <trigger>. ADR: <link>

Shipped: <thing> in tapesift.
Before: <number>. After: <number>. Same machine.
How: <one line>. <link>

Broke: <what>.
Cause: <root cause>.
Fix: <fix>. Lesson: <one line>.
```

**Devlog pipeline**

1. Each evening the `log` pane agent reads the day's `git log`, merged PRs and new ADRs, and writes `devlog/drafts/YYYY-MM-DD.md` with up to 3 draft posts.
2. You rewrite them in your voice (your `/human` skill) and post.
3. `devlog/` keeps the archive, linked from the README.

**Vlog shape:** the number this week (1 min), the decision and why (3 min), what broke (3 min), your agents working live in herdr (2 min), next week (1 min). Footage of five agents running in one terminal is content in its own right; few people show it honestly.

**Each write-up feeds outreach.** Send it with its specific number to 5 people whose work it touches:

| Milestone | Who to send it to |
| --- | --- |
| v0.2 cost write-up | Inference platforms (Modal, Baseten, Fal, Together) |
| v0.4 launch | Video understanding and video-gen data teams |
| Y1 injection benchmark | Safety and security teams at labs and agent companies |
| T5 rollout result | RL infrastructure teams |
| R2 self-training curve | Post-training teams at labs |

**Rules:** never post a number you can't reproduce with a command. Credit tools and people by name. Reply to others with numbers, not compliments.

## Business validation

Ten buyer conversations by Dec 15. If 3 describe a real cost and agree to a pilot, treat tapesift as a company and use the numbers in an accelerator application. If not, it's still your strongest portfolio piece, and every conversation was a contact.

| Segment | Who to talk to | Their footage | Likely pain |
| --- | --- | --- | --- |
| Media archives and broadcast | Archive, library and media-asset managers | Decades of footage, thin metadata | Finding clips; manual logging |
| Litigation support | Litigation support and e-discovery managers | Depositions, recorded meetings | Review hours; footage can't leave the network |
| Insurance claims | Claims operations and innovation leads | Claimant videos, inspections | Manual review time per claim |
| Edtech and corporate training | Platform and L&D teams | Lectures, trainings, webinars | Search inside long videos |
| AI data teams | Data leads at video-gen, world-model and robotics startups | Raw footage for training | Curation cost per hour |

**Questions to ask** (listen; don't pitch until the last one):

1. What video or audio do you have, and roughly how many hours come in each month?
2. Walk me through the last time you needed to find something in it.
3. What does that cost today, in people-hours, tools or API bills?
4. Can the footage leave your network? Who decides that?
5. What have you tried, and why didn't it stick?
6. If something did this on your own servers for a known cost per hour, what would you need to see to try it?

Real signals: a recent painful example with numbers, a request to try it, an introduction to whoever owns the budget. Compliments don't count.

**Pricing hypotheses to test, not announce:** self-hosting stays free; paid tiers are a managed version priced per video-hour, on-prem deployment with support, and a domain pack tuned on the customer's corrections. Question 3 tells you the ceiling.

**Conversation log**

| Date | Role | Segment | Hours per month | Current cost | Pilot? | Next step |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## Calendar and weekly rhythm

The public launch on Dec 6 is the date everything bends around; v1.0 follows on Jan 31.

&#91;embedded content: build timeline · 7 phases, 6 milestones\]

Thanksgiving week falls inside v0.3, so v0.3 is the release most likely to slip. Let it slip rather than the launch.

**A normal week** (about 14 hours, decision D10)

| When | Time | What |
| --- | --- | --- |
| Weekday morning | 20 min | Lead session: answer blocked agents, merge done PRs, write 2 to 3 briefs, dispatch |
| Weekday evening | 90 min | Deep review of 1 to 2 PRs, your hand-written piece, ADRs |
| Daily | 2 min | Talk-out-loud note while reviewing a PR |
| Daily | 10 min | Edit and post one devlog draft |
| Friday | 45 min | Numbers thread; check the step gate; release if exit criteria are met |
| Saturday | 4 h | GPU session over `herdr --remote` (bench or training), record the vlog, one buyer or outreach conversation |
| Sunday | 30 min | Publish the vlog; label next week's `agent-ready` issues; rest |

**Weeks that change shape**

- The Lexsi hackathon week in November: agents run docs and maintenance only, and your hours go to the hackathon.
- Release weeks: no new features after Wednesday; Thursday and Friday are for install tests and the write-up.
- Each release triggers the outreach row for it in Build in public, so the job search and the build feed each other.

## Sources

Tool commands were checked against these pages on Oct 13, 2026. Agent tools change monthly, so recheck a command against its page if it errors.

- [Steps of AI Adoption](https://claude.ai/code/artifact/bfdfaef9-bc62-4dfe-ba9e-c58a26c9accf), Boris Cherny: the step 0 to 4 ladder this plan's gates follow
- [Claude Code: Configure auto mode](https://code.claude.com/docs/en/auto-mode-config): `permissions.ask` checkpoints, `autoMode.environment`, `/auto-mode-setup`
- [Claude Code: Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees): `claude --worktree`, `.worktreeinclude`, `isolation: worktree`
- [Claude Code: Run agents in parallel](https://code.claude.com/docs/en/agents): subagents, agent view (`claude agents`), `/batch`, routines
- [Claude Code: Dynamic workflows](https://code.claude.com/docs/en/workflows): workflows, `/workflows`, saving, size guideline
- [herdr](https://herdr.dev): install script, Apache-2.0 license
- [herdr agent automation](https://herdr.dev/docs/agent-automation/): `herdr agent start`, `prompt`, `wait`, `read`
- [herdr on GitHub](https://github.com/ogulcancelik/herdr): agent skill install command (taken from the README as indexed; confirm when you install)

Positioning sources, checked Oct 13, 2026:

- [Twelve Labs pricing](https://usagepricing.com/blueprint/twelve-labs) (UsagePricing capture of the public pricing page)
- [VideoDB SDK README](https://cdn.jsdelivr.net/npm/videodb@0.2.7/Readme.md)
- [Mixpeek: Twelve Labs alternative](https://mixpeek.com/blog/twelve-labs-alternative) (vendor's own claims)
- [NVIDIA VSS overview](https://docs.nvidia.com/vss/3.0.0/overview/3.0.0/)
- [NeMo Curator video curation](https://docs.nvidia.com/nemo/curator/latest/get-started/video.html)
- [Edit Mind](https://selfhostyourself.com/services/edit-mind)
- [SentrySearch](https://feedbagel.com/post/sentrysearch-open-source-semantic-video-search-tool-using-gemini-embedding-2)
