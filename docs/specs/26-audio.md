# 26. E3: audio — VAD gate, faster-whisper word timestamps, phantom-phrase filter, chunk seams (absorbs #13)

Issue: #26 (absorbs #13)   Lane: Core, plus `src/tapesift/eval/wer.py` (an Eval-lane path issue #26 grants)   Status: draft r3 (lean mode). Every card is decided (below); ready for the lead to approve.
Revisions: 2026-10-20 r2 answered spec-critic findings 1-12. 2026-10-20 r3, lean mode (owner: working MVP demo first; opus decides, sonnet builds): cards decided; tests cut from 118 local to 34; the quietest-frame seam fallback, the host audit test, third-party phantom data and the nightly job are cut (see "Later").

Planned against the merged M1 interfaces (`docs/specs/25-m1-interfaces.md`, main 7bcb1ee). Uses only M1 names and redefines no M1 type, Protocol, config key or fake. If a merged name differs, stop and raise a card.

## Decisions (opus, 2026-10-20, lean mode; owner delegated)
| Card | Choice | Why |
| --- | --- | --- |
| 1 (T3, privacy) `*.hf.co` hosts in `doctor` | **A, text only**: the first `NETWORK_CALLS` entry names `*.hf.co` storage hosts. The audit-hook host test is cut (Later) | The privacy statement must be true (HF redirects weights to `*.hf.co`, observed). One line; the test needs a cold fetch and an audit-hook subprocess, which the demo doesn't need |
| 2 (T3, licensing) phantom list source | **C**: only the spec's own family (`Thank you.`, `Thanks for watching!`, `Thank you for watching.`). No third-party data, no THIRD_PARTY.md or MIT notice | Zero licensing surface in the wheel; covers the phantoms that matter most (Table III's top two are in it). Grow the list by card later |
| 3 (T2) 60 s speech floor on `LOW_SPEECH` | **A**: `LOW_SPEECH` only when ratio < threshold **and** speech < `KEEP_SPEECH_S = 60.0`; edit the spec 246 comment | One condition; stops a long, mostly silent recording losing all its talk |
| 4 (T2, CI minutes) measure WER before approval | **C**: no pre-measurement. The first `models` run on E3's draft PR is the measurement | Saves a separate experiment branch. If WER > 0.20 the builder stops and reports the hypothesis and normalized diff; the lead decides the bound or model by card |
| new T1 | Seam fallback: with no VAD gap in the last 30 s, cut hard at the buffer end (no quietest-frame search) | 30 s of gapless speech is rare in talks; at worst one word splits at that seam. `ponytail:` comment, upgrade path in Later |
| new T1 | One `models.yml` job runs **every** `model`-marked test with `uv sync --all-extras` and one HF cache keyed on all pins | E4, E6 and E7 add model tests without editing `.github/` |

Nothing here spends money or touches credentials. The `models` job uses the private repo's Actions minutes (owner Q4 A).

## Goal
`tapesift.audio.stage.transcribe_asset` (signature fixed by M1) turns one asset's audio into sorted, clamped `Utterance`s with word timestamps from the pinned faster-whisper model. It:
- skips ASR, and emits `LOW_SPEECH`, when the bundled Silero VAD finds too little speech;
- drops known phantom phrases where the VAD heard no speech;
- cuts 600 s chunk seams in VAD silence, so each spoken word is transcribed once (#13).

A Linux-only `models` workflow runs the real models and pins WER ≤ 0.20 on speech.mp4 (Q8 A), at 600 s and at 2 s chunks.

## Read first
- `docs/specs/25-m1-interfaces.md`: `Utterance`, `Word`, `clamp_utterance`, `AssetRecord`, `Provenance`; `VAD`, `ASR`; `AsrConfig`, `ASR_MODELS`, `ModelPin`, `Profile`, `ModelLoadError`, `fetch_pin`; the `transcribe_asset`, `SileroVAD`, `FasterWhisperASR` signatures; R1-R6 and **R8** (streaming; the tracemalloc test is an owner-required E3 acceptance item; seams; 0.1 s overlap); the `FakeVAD` and `FakeASR` rows; Risks "Xet storage".
- `docs/specs/4-media-types.md`: `AudioChunk` (copies a view), R1, R8 (runs, `AUDIO_GAP_FILL_S`), R10, the emitter table (E3 owns `LOW_SPEECH`).
- `docs/specs/6-decode.md`: `iter_audio` (a fresh buffer per chunk; last chunk trimmed at `duration_s`).
- docs/spec.md: 56 and ADR 0010 (English only; detected language recorded per utterance), 184, 198, 243-248, 264-281, 295-297, 337, 524-525, 737.
- ADRs 0007, 0008, 0010.
- Code: `src/tapesift/media/decode.py`, `src/tapesift/media/types.py`, `src/tapesift/warning_codes.py`, `src/tapesift/cli/doctor.py` (`NETWORK_CALLS`), `tests/smoke/conftest.py`, `tests/contract/test_vad.py` and `test_asr.py` (fixture form: zero-argument factories), `.github/workflows/ci.yml` (actions pinned by SHA), `tests/fixtures/manifest.json` (speech.mp4 transcript, 15 words).
- **faster-whisper 1.2.1** (read at tag v1.2.1, 2026-10-20):
  - `WhisperModel(path, device, compute_type)` with a directory skips `download_model`; the pinned `tokenizer.json` skips the `openai/whisper-tiny` network fallback.
  - `transcribe(audio, language=None, word_timestamps=False, vad_filter=False, ...)` returns `(lazy segments, info)`. Temperatures above 0 sample; `ctranslate2.set_random_seed(seed)` exists (4.8.3).
  - `Segment`: `start, end, text, avg_logprob, no_speech_prob, words`; `Word`: `start, end, word, probability`; `info.language` is ISO 639-1.
  - `faster_whisper.vad.get_speech_timestamps(audio, VadOptions, sampling_rate)` runs the bundled `silero_vad_v6.onnx` in 512-sample windows (16 kHz only).
  - No `py.typed`.
- **Observed, 2026-10-20** (scratch venv: faster-whisper 1.2.1, onnxruntime 1.31.0, ctranslate2 4.8.3, av 19.0.1; Silero is package data, allowed on the laptop by Q5), `VadOptions(min_silence_duration_ms=500, speech_pad_ms=200)`:

  | Input | spans | speech ratio |
  | --- | --- | --- |
  | speech.mp4 (6.9925 s audio, stream 1) | `[(0.0, 6.992)]` | 1.000 |
  | speech.mp4 at `chunk_s=2.0` | `(0,2)`, `(2,4)`, `(4,6)`, `(6,6.992)`: one span once joined | 1.000 |
  | speech.mp4 at `chunk_s=3.0` | a 0.056 s chunk-start artifact at 3.0 | 1.000 |
  | silence.mp4 (4.0 s), music.m4a (6.0 s, stream 0), every tone fixture | `[]` | 0.000 |
  | contract `BURSTS`, `TONE`, `ZEROS` | `[]` | n/a |

  Imports are clean under `python -W error`. Silero accepts a read-only array. `WhisperModel(<empty dir>)` raises `RuntimeError: Unable to open file 'model.bin' ...` with no network use.
- **Hosts (card 1).** The HF tree API shows both pinned `model.bin`s on Xet; `HEAD .../resolve/<rev>/model.bin` returns `302` to `https://us.aws.cdn.hf.co/...`, with a `Link` to `cas-server.xethub.hf.co`. All Hugging Face; no third party.

## Scope
May change (new unless marked):
- `src/tapesift/audio/stage.py`, `src/tapesift/audio/vad.py`, `src/tapesift/audio/faster_whisper.py`, `src/tapesift/audio/phantoms.py`
- `src/tapesift/eval/__init__.py` (one-line docstring), `src/tapesift/eval/wer.py`
- `tests/unit/test_audio_stage.py`, `tests/unit/test_audio_faster_whisper.py`, `tests/unit/test_wer.py`
- `tests/smoke/test_audio_stage.py`; `tests/smoke/test_asr_models.py` (`pytestmark = pytest.mark.model`)
- `.github/workflows/models.yml`, exactly as below. `ci.yml` is not touched.
- Shared files (keep every line at rebase):
  - `tests/contract/test_vad.py`: one param `pytest.param(lambda: SileroVAD(Config()), id="silero")` (no marker, Q5), plus imports;
  - `tests/contract/test_asr.py`: one param `pytest.param(lambda: FasterWhisperASR(Config()), id="faster-whisper", marks=pytest.mark.model)`, plus imports;
  - `src/tapesift/cli/doctor.py`: the first `NETWORK_CALLS` string only (card 1);
  - `docs/spec.md`: the comment on line 246 only (card 3);
  - `CHANGELOG.md`: one line under Unreleased, Added: `- Audio stage: Silero VAD gate with LOW_SPEECH, faster-whisper word timestamps, a phantom-phrase filter and silence-aligned chunk seams; a Linux "models" workflow runs the real models (#26, #13).`
- Merge order: E3 needs M1 on main (it is). E3 creates `models.yml`; nobody else creates or edits it.

Must not touch:
- M1's files: `src/tapesift/audio/types.py`, `src/tapesift/audio/__init__.py`, `src/tapesift/schema/**`, `src/tapesift/config.py`, `src/tapesift/hub.py`, `tests/fakes.py`, other `tests/contract/*` files.
- `src/tapesift/media/**`, `src/tapesift/warning_codes.py`, `pyproject.toml`, `uv.lock`, `Makefile`, `.github/workflows/ci.yml`, `THIRD_PARTY.md`.
- `src/tapesift/{vision,store,runner,pipeline}/**`, `src/tapesift/cli/**` (except the one string), the rest of `docs/spec.md`, `README.md`, `tests/fixtures/**`, `scripts/**`, `AGENTS.md`, `CLAUDE.md`, `.claude/**`.
- Every existing test, except the two contract params.

## Interfaces touched
Before: M1's `audio/types.py` and the fixed signatures only. After: the following. Docstrings are part of the contract. "Pure" means no I/O, tested directly.

### `src/tapesift/audio/stage.py`
```python
"""E3: one asset's audio to Utterances (docs/specs/26-audio.md S1-S8; M1 R2, R8)."""

SAMPLE_RATE: Final = 16_000
MAX_CARRY_S: Final = 30.0  # longest tail held back for the next chunk at a seam (S2)
MIN_PIECE_S: Final = 1.0  # a seam cut leaves at least this much audio before it (S2)
SPAN_JOIN_S: Final = 0.3  # VAD spans with a smaller gap are one span; absorbs chunk-edge artifacts
KEEP_SPEECH_S: Final = 60.0  # never LOW_SPEECH with at least this much VAD speech (card 3)
MAX_OVERLAP_S: Final = 0.1  # consecutive utterances overlap by at most this (M1)
CLAMP_WARN_S: Final = 0.5  # a clamp moving a time by more than this logs one WARNING (M1 R2)

Span = tuple[float, float]


def merge_spans(spans: Iterable[Span], join_s: float = SPAN_JOIN_S) -> list[Span]:
    """Pure. Sorted union of the spans with b > a; spans whose gap (next a - current b) is below
    join_s, overlaps and touches included, become one."""


def covered_s(speech: Sequence[Span], start_s: float, end_s: float) -> float:
    """Pure. Seconds of [start_s, end_s] inside the merged spans `speech`."""


def low_speech_detail(index: int, speech_s: float, audio_s: float, threshold: float) -> str | None:
    """Pure (S3). The LOW_SPEECH detail, or None to run ASR:
    audio_s == 0: f"audio stream {index}: no audio samples decoded";
    speech_s == 0: f"audio stream {index}: VAD found no speech in {audio_s:.1f} s";
    speech_s < KEEP_SPEECH_S and speech_s / audio_s < threshold:
      f"audio stream {index}: VAD speech {speech_s:.1f} s of {audio_s:.1f} s, ratio {ratio:.3f} < {threshold:g}";
    else None."""


def seam_cut(
    start_s: float, end_s: float, speech: Sequence[Span], max_carry_s: float = MAX_CARRY_S
) -> float:
    """Pure (S2). Where to cut the buffer [start_s, end_s); `speech` is merge_spans output.
    1. end_s is in silence (no span with a <= end_s <= b): end_s.
    2. Else the latest gap midpoint m = (b_i + a_{i+1}) / 2 with m - start_s >= MIN_PIECE_S,
       m < end_s and m >= end_s - max_carry_s.
    3. Else start_s, when end_s - start_s <= max_carry_s (hold the whole buffer back).
    4. Else end_s: a hard cut (no gap in the last max_carry_s seconds of a longer buffer)."""
    # ponytail: rule 4 may split one word inside 30 s+ of gapless speech; upgrade: cut at the
    # quietest 50 ms frame of the last 30 s (#13 r2 design, see Later).


def transcribe_asset(
    asset: AssetInfo, decoder: Decoder, vad: VAD, asr: ASR, cfg: Config, *, warn: WarningSink
) -> list[Utterance]:
    """(M1's docstring, verbatim.)"""
```

### `src/tapesift/audio/vad.py`
```python
"""SileroVAD: Silero v6 ONNX, bundled in faster-whisper (owner Q5: laptop tests, no fetch)."""

SILERO_OPTIONS: Final = {"threshold": 0.5, "min_silence_duration_ms": 500, "speech_pad_ms": 200}


class SileroVAD:
    def __init__(self, cfg: Config) -> None:
        """Imports faster_whisper.vad here (R6) and loads the model once (get_vad_model()).
        Any exception becomes ModelLoadError(f"cannot load Silero VAD: {type(e).__name__}: {e}").
        cfg is unused in v0.1."""

    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]:
        """M1 VAD. get_speech_timestamps(chunk.samples, VadOptions(**SILERO_OPTIONS),
        sampling_rate=16000), each index i mapped to chunk.start_s + i / 16000.
        ValueError if chunk.sample_rate != 16000."""
```

### `src/tapesift/audio/faster_whisper.py`
```python
"""FasterWhisperASR: ASR_MODELS[cfg.asr.model] through tapesift.hub.fetch_pin (M1 R4).
faster_whisper and ctranslate2 are imported inside __init__ only (R6)."""

from tapesift.hub import fetch_pin  # tests patch tapesift.audio.faster_whisper.fetch_pin

MAX_END_OVERSHOOT_S: Final = 1.0  # M1 ASR contract
SEED: Final = 0  # ctranslate2.set_random_seed(SEED) before every model.transcribe (spec 737)
TRANSCRIBE_KWARGS: Final = {"language": None, "word_timestamps": True, "vad_filter": False}
"""Everything else is a faster-whisper 1.2.1 default, including the temperature fallback.
language None: Whisper detects per call and the utterance records it (ADR 0010).
vad_filter off: the stage's VAD is the only detector (M1 R8)."""


def device_for(profile: Profile | None) -> Literal["cpu", "cuda"]:
    """Pure. "cuda" for GPU and SERVER, else "cpu" (None counts as cpu)."""


def to_utterance(
    start: float, end: float, text: str, avg_logprob: float,
    words: Sequence[tuple[str, float, float]],
    *, lang: str | None, chunk_start_s: float, chunk_end_s: float,
) -> Utterance | None:
    """Pure. One segment (chunk-relative times) to an Utterance on the container clock; None when
    text.strip() is empty. With c(t, a, b) = min(max(t, a), b):
    s = c(start + chunk_start_s, chunk_start_s, chunk_end_s);
    e = c(end + chunk_start_s, s, chunk_end_s + MAX_END_OVERSHOOT_S);
    conf = min(1.0, exp(avg_logprob)), or 0.0 when avg_logprob is not finite;
    words = (w.strip(), ws = c(w_start + chunk_start_s, s, e), c(w_end + chunk_start_s, ws, e)),
    blank words dropped, sorted by ws; text = text.strip()."""


class FasterWhisperASR:
    def __init__(self, cfg: Config) -> None:
        """pin = ASR_MODELS[cfg.asr.model]; d = fetch_pin(pin) (ModelLoadError passes through);
        WhisperModel(str(d), device=device_for(cfg.profile), compute_type=cfg.asr.compute_type).
        Any exception from WhisperModel becomes
        ModelLoadError(f"cannot load {pin.repo}@{pin.revision[:12]}: {type(e).__name__}: {e}")."""

    @property
    def id(self) -> str:
        """ASR_MODELS[cfg.asr.model].id."""

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        """M1 ASR. Per chunk: set_random_seed(SEED); model.transcribe(chunk.samples,
        **TRANSCRIBE_KWARGS), the generator consumed; each segment through to_utterance with
        lang=info.language and the chunk's bounds; None dropped. Exceptions propagate (R5)."""
```

### `src/tapesift/audio/phantoms.py`
```python
"""Whisper phantom phrases on non-speech audio (spec row "Silence or music only", card 2 C).
The project's own short list; no third-party data."""

PHANTOM_PHRASES: Final[tuple[str, ...]] = (
    "Thank you.",
    "Thanks for watching!",  # docs/spec.md row 297
    "Thank you for watching.",
)
MAX_SPEECH_SHARE: Final = 0.5  # a listed phrase is dropped only if VAD covers at most this share


def is_phantom_text(text: str) -> bool:
    """The WHOLE utterance matches: tapesift.eval.wer.normalize(text) equals a normalized
    PHANTOM_PHRASES entry. No substring match."""
```

### `src/tapesift/eval/wer.py`
```python
"""Word error rate and its normalizer (owner Q8 A). Pure stdlib; V2 reuses both."""


def normalize(text: str) -> str:
    """1. unicodedata.normalize("NFKC", text).lower()
    2. thousands separators dropped: re.sub(r"(?<=\\d),(?=\\d{3}\\b)", "", t)
    3. ":00" after a number dropped: re.sub(r"(\\d):00\\b", r"\\1", t)
    4. "%" -> " percent "
    5. each r"\\d+(?:\\.\\d+)?" -> English words: integers below one million without "and"
       (0 "zero", 105 "one hundred five", 2021 "two thousand twenty one"), longer integers
       digit by digit; a fraction is "point" plus one word per digit
    6. re.sub(r"[\\W_]+", " ", t).strip()"""


def wer(reference: str, hypothesis: str) -> float:
    """(S + D + I) / reference word count, by word-level Levenshtein on normalize()d text split
    on spaces. ValueError if the normalized reference is empty."""
```

### Rules (E3 implements every one)
**S1. Track, two passes, spans.**
- **No audio.** `asset.audio == ()` returns `[]`; decoder, VAD and ASR are never called; no warning.
- **Track.** `t = cfg.asr.audio_track`. Out of range: one WARNING `asr.audio_track {t} not in 0..{len(asset.audio) - 1}; using the default track`, then `t = None`. Stream index `i` is `asset.audio[t].index`, or `asset.default_audio.index` when `t` is None.
- **Pass 1 (VAD).** `decoder.iter_audio(asset, SAMPLE_RATE, track=t, chunk_s=cfg.asr.batch_seconds, warn=sink1)`; `vad.speech_spans(c)` once per chunk; keep only the spans and `n1`, the total sample count. `sink1` records each warning in `seen` and forwards it.
- **Pass 2 (ASR).** The same call with `sink2`, which forwards only warnings not in `seen`. The VAD is not called again.
- **Pass mismatch.** If `n2 != n1`, one WARNING `audio decode differed between passes: {n1} vs {n2} samples`; keep pass 2's output; pass-1 spans still drive the cuts.
- Why two passes: `LOW_SPEECH` is per file and is decided before any ASR call (M1).
- `speech = merge_spans(all pass-1 spans)`. A `StageError` from the decoder propagates.

**S2. Seams (#13, M1 R8).** Cut in VAD silence and carry the tail into the next chunk. Pieces never overlap, so nothing needs de-duplicating.
- `carry`: samples held back from earlier chunks. Always owned memory (never a view; a view would pin the decoder's 38.4 MB array), at most `MAX_CARRY_S` long.
- For each chunk `c`:
  1. **Run break.** If `carry` exists and `abs(c.start_s - carry_end) > 0.5 / SAMPLE_RATE`, flush `carry` as a piece and continue with no carry.
  2. **Buffer** `carry ++ c`, spanning `[buf_start, buf_end)` (not materialized).
  3. **Cut.** `cut = seam_cut(buf_start, buf_end, speech)`. Sample index `floor((t - buf_start) * SAMPLE_RATE + 0.5)`.
  4. **Piece `[buf_start, cut)`, new carry `[cut, buf_end)`.** No carry and `cut == buf_end`: the piece is `c` itself. No carry and `cut < buf_end`: `AudioChunk(c.start_s, c.samples[:k], ...)` (it copies). With a carry: a new owned array `carry ++ c.samples[:k]`. New carry: `c.samples[k:].copy()`, or `np.concatenate([carry, c.samples])` when holding everything back.
  5. **Send.** A non-empty piece with `covered_s(speech, piece) > 0` goes alone to `asr.transcribe([piece])`. A piece with no speech is never sent.
  6. **Release.** `del` the references to `c`, the piece and the old carry before the next `next()`.
- After the last chunk, flush `carry` the same way, at any length.
- On speech.mp4 at `chunk_s=2.0`, the joined span `(0, 6.992)` holds every buffer back, and the flush sends one piece `[0, 6.9925)`: the same audio as at 600 s.

**S3. Gate (`LOW_SPEECH`).**
- `audio_s = n1 / SAMPLE_RATE` (the selected track as decoded, trimmed at `duration_s`); `speech_s = covered_s(speech, 0.0, inf)`.
- `d = low_speech_detail(i, speech_s, audio_s, cfg.asr.vad_min_speech_ratio)`. If not None: `warn(AssetWarning(LOW_SPEECH, d))` and return `[]` with no pass 2. A ratio exactly at the threshold runs ASR. `speech_s == 0` always gives `LOW_SPEECH`, even with threshold 0.0.
- **Contract E7 relies on for `provenance.asr`:** a normal return has called `asr.transcribe` at least once iff `asset.audio` is non-empty and no `LOW_SPEECH` was sent (speech_s > 0 means some piece has `covered_s > 0` and is sent).

**S4. Clamp, phantoms, overlap, in this order.**
1. **Clamp.** Each utterance through `clamp_utterance(u, piece.start_s, hi)`, `hi = min(piece_end, duration_s)` (or `piece_end` when `duration_s` is None). None is dropped. If any clamp moved a time by more than `CLAMP_WARN_S`, exactly one WARNING per asset: `ASR times moved up to {shift:.2f} s by clamping`.
2. **Phantoms** (S5), before the overlap cap, so a dropped phantom never shortens a neighbour.
3. **Overlap.** For each consecutive pair with `prev.end_s > next.start_s + MAX_OVERLAP_S`, `prev = clamp_utterance(prev, prev.start_s, next.start_s + MAX_OVERLAP_S)`.

The output is sorted, every time is inside `[0, duration_s]`, and an `AssetRecord` built from it never raises.

**S5. Phantoms.** Drop `u` if `is_phantom_text(u.text)` and `covered_s(speech, u.start_s, u.end_s) <= MAX_SPEECH_SHARE * (u.end_s - u.start_s)` (a zero-length match is dropped). One INFO line per asset that dropped any: `dropped phantom phrases: "thank you" x2, "thanks for watching" x1`. Not a warning code.

**S6. Backends.** `FasterWhisperASR` loads only from `fetch_pin`'s directory. faster-whisper has no `py.typed`: `# pyright: ignore[reportMissingTypeStubs]` on its import lines only, and `cast` untyped values. `set_random_seed(SEED)` before each call makes each piece's output independent of call order. `SileroVAD` makes no network call.

**S7. Logging.** `logging.getLogger(__name__)` per module, with `extra={"asset_id": asset.id, "stage": "asr"}` in the stage. Never `print`. Never log transcript text.

**S8. Memory (M1 R8, owner-required test).** Largest live set, independent of file length: the decoder's chunk (`CHUNK_BYTES = 600 * 16000 * 4 = 38_400_000`), plus piece and new carry together (`40_320_000`), plus the old carry while the piece is built (`1_920_000`): **80 640 000 bytes** plus the backends' own temporaries.

### `doctor.py` edit (card 1)
The first `NETWORK_CALLS` entry becomes exactly: `huggingface.co and Hugging Face storage hosts under *.hf.co (CDN, Xet): model weights, on first use or \`tapesift models pull\``.

### `docs/spec.md` edit (card 3)
The comment on line 246 becomes `# below this, and under 60 s of speech in total, skip ASR for the file`.

### `.github/workflows/models.yml` (owner Q4 A)
```yaml
name: models

# Real pinned models (owner Q4 A, 2026-10-19). Linux only. Advisory (not a required check).
# Runs every `model`-marked test, so E4, E6 and E7 add tests without editing this file.
# Never run model tests on the laptop (ADR 0008).

on:
  pull_request:
    paths-ignore: ["docs/**", "devlog/**", "**.md"]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: models-${{ github.ref }}
  cancel-in-progress: true

env:
  UV_LOCKED: "1"
  FORCE_COLOR: "1"

jobs:
  models:
    name: real models (Linux)
    runs-on: ubuntu-latest
    timeout-minutes: 45 # E3 about 10, E4 about 15, E6 and E7 a few each
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0
        with:
          enable-cache: true
      - run: uv sync --locked --all-extras # vision extra; torch from M1's CPU index on Linux
      - id: pins
        run: |
          echo "key=$(uv run python -c 'from tapesift.config import ASR_MODELS, VLM_MODELS, EMBEDDER; print("-".join(p.revision[:12] for p in (*ASR_MODELS.values(), *VLM_MODELS.values(), EMBEDDER)))')" >> "$GITHUB_OUTPUT"
      - id: restore
        uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: ~/.cache/huggingface/hub
          key: hf-${{ steps.pins.outputs.key }}
      - run: uv run pytest -m model -q -o log_cli=true --log-cli-level=INFO
      # Saved even when a test fails: the download itself succeeded.
      - if: always() && steps.pins.outcome == 'success' && steps.restore.outputs.cache-hit != 'true'
        uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: ~/.cache/huggingface/hub
          key: ${{ steps.restore.outputs.cache-primary-key }}
```
No `continue-on-error`: advisory means not required, not hidden. `actions/cache` v6.1.0 = `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` (checked with `gh api`).

## Acceptance
**Helpers** (in `tests/unit/test_audio_stage.py`; smoke files use real objects):
- `ListDecoder(chunks_per_call, warnings=())` implements `Decoder`: records each `iter_audio` call's kwargs in `calls`, sends `warnings` through `warn`, yields that call's `AudioChunk`s (created inline in `yield`) or slices a sample array into `chunk_s` pieces; `iter_frames` yields nothing.
- `ScriptedVAD(spans)` returns global spans clipped to each chunk and counts calls. `ScriptedASR(fn)` records `(piece.start_s, piece_end)` per call and returns `fn(piece)`.
- `BLOCK` is 10 s at 16 kHz: 18 × (0.3 s of 440 Hz at 0.3, then 0.2 s of zeros), tones ending at 8.8 s, then 1.2 s of zeros. FakeVAD gives `(0.0, 8.8)` within 0.02.
- Assets: `AssetInfo` literals with `id = "tsid1:" + "0" * 64`, `video=None`, `warnings=()`, `audio=(AudioStreamInfo(1, "aac", None, True),)` unless a row says otherwise.

`...` means `uv run pytest <file> -q`.

| # | Rule / case | Command | Expected |
| --- | --- | --- | --- |
| 1 | `merge_spans`, `covered_s` | `... tests/unit/test_audio_stage.py -k "test_merge_spans or test_covered_s"` | `2 passed`. merge: `[]` gives `[]`; `[(2,3),(0,1)]` gives `[(0,1),(2,3)]`; `[(0,2),(1,3)]` gives `[(0,3)]`; `[(0,1),(1.25,2)]` gives `[(0,2)]`; `[(0,1),(1.5,2),(3,3)]` gives `[(0,1),(1.5,2)]`. covered: `([],0,10)` 0.0; `([(1,2),(3,5)],0,4)` 2.0 |
| 2 | `seam_cut` | `... -k test_seam_cut` | `5 passed`, each `(speech, start, end)`: **end_in_silence** `([(1,3)],0,10)` gives 10; **gap_in_window** `([(0,5),(6,12)],0,10)` gives 5.5; **short_held_back** `([(0,12)],0,10)` gives 0; **gap_too_close_to_start** `([(0,0.4),(0.6,12)],0,10)` gives 0; **no_gap_long_hard_cut** `([(0,2),(3,40)],0,38)` gives 38 |
| 3 | `low_speech_detail` | `... -k test_low_speech_detail` | `1 passed`: `(0,0,0.05)` gives `audio stream 1: no audio samples decoded`; `(0,4.0,0.0)` gives `audio stream 1: VAD found no speech in 4.0 s`; `(0.0625,1.0,0.0625)` gives None; **floor** `(480.0,10800.0,0.05)` gives None; **under floor** `(59.9,10800.0,0.05)` gives `audio stream 1: VAD speech 59.9 s of 10800.0 s, ratio 0.006 < 0.05` |
| 4 | S1: no audio | `... -k test_no_audio` | `1 passed`: `[]`; `decoder.calls == []`; `FakeASR().calls == []`; empty sink |
| 5 | S3: gate in the stage | `... -k test_low_speech_gate` | `2 passed`. 1.0 s chunk, `ScriptedVAD`, `FakeASR`, threshold 0.0625. **below** span `(0,0.03125)`: `[]`, sink exactly `[AssetWarning(LOW_SPEECH, "audio stream 1: VAD speech 0.0 s of 1.0 s, ratio 0.031 < 0.0625")]`, `asr.calls == []`, one decode pass. **above** `(0,0.125)`: no warning, `asr.calls == [1]` |
| 6 | S1: track out of range | `... -k test_audio_track_out_of_range` | `1 passed`: two streams (1 and 2), 1 s of zeros, `audio_track = 5`: `track=None` in every call, detail `audio stream 1: VAD found no speech in 1.0 s`, exactly one WARNING `asr.audio_track 5 not in 0..1; using the default track` |
| 7 | S1: warnings once | `... -k test_decode_warning_once` | `1 passed`: a `PARTIAL_DECODE` sent in both passes reaches the sink once |
| 8 | S2: each span once across seams | `... -k test_each_span_once` | `2 passed` (chunk_s 1.0 and 600.0): two `BLOCK`s through `FakeVAD` and `FakeASR` give exactly 2 utterances `"fake speech"`, within 0.02 of `(0.0,8.8)` and `(10.0,18.8)` |
| 9 | S4: clamp inside duration | `... -k test_clamp_inside_duration` | `1 passed`: `BLOCK` trimmed to 9.0, `duration_s=9.0`, `FakeASR(overshoot_s=0.5)`: last end and last word end are 9.0; `AssetRecord(asset, tuple(out), (), (), Provenance("0.1.0", FakeASR().id, None, None))` builds |
| 10 | S4: overlap cap | `... -k test_overlap_cap` | `1 passed`: `(0,5)` with words `(0,2)`, `(2,5)`, then `(4,8)`: the first becomes `(0,4.1)` with last word `(2,4.1)` |
| 11 | S5: phantoms | `... -k "test_phantom or test_is_phantom_text"` | `3 passed`. 10 s chunk, VAD `[(0,4)]`: **in_speech_kept** `"Thanks for watching!"` at (1,2) is kept; **in_silence_dropped** the same at (5,6) is dropped, with one INFO `dropped phantom phrases: "thanks for watching" x1`. `test_is_phantom_text`: True for `"Thanks for watching!"` and `"THANK YOU."`; False for `"Thank you for coming."`, `""` and `"Thanks for watching and see you"` |
| 12 | S8: M1 R8 memory test | `... -k test_streaming_memory_bound` | `1 passed` (marked `slow`). A 600 s template of 60 `BLOCK`s built before tracing; a stub yields `AudioChunk(k*600.0, template.copy(), 16000)` inline; `FakeVAD`, `FakeASR`, `duration_s = n*600.0`. `fakes` is the tracemalloc peak of `FakeVAD().speech_spans(c630)` plus `FakeASR().transcribe([c630])` on a 630 s chunk allocated before tracing. **(a)** `peak(6) <= fakes + 80_640_000 + 4 * 2**20`. **(b)** `abs(peak(12) - peak(6)) <= 0.10 * peak(6)`. **(c)** `len(out) == 60 * n` for both. The PR reports the three peaks |
| 13 | Normalizer and WER | `... tests/unit/test_wer.py` | `2 passed`. `test_normalize`: `"Revenue grew 12% while costs stayed flat."` gives `"revenue grew twelve percent while costs stayed flat"`; `"at 9:00"` gives `"at nine"`; `"1,000"` gives `"one thousand"`; `"12.5"` gives `"twelve point five"`; `"2021"` gives `"two thousand twenty one"`; `"I'm here."` gives `"i m here"`. `test_wer`: identical gives 0.0; `"a b c d"` vs `"a x c d"` gives 0.25; empty hypothesis gives 1.0; reference `"..."` raises `ValueError`; the manifest transcript vs `"The quarterly pricing review starts at 9:00. Revenue grew 12% while costs stayed flat."` gives 0.0 |
| 14 | faster-whisper helpers, no weights | `... tests/unit/test_audio_faster_whisper.py` | `4 passed`. **`test_to_utterance`**: `(1.0,2.0," Hello there. ",-0.5,[(" Hello",1.0,1.4),(" there.",1.4,2.0)], lang="en", chunk 600-610)` gives `Utterance(601.0,602.0,"Hello there.","en",exp(-0.5),(Word("Hello",601.0,601.4),Word("there.",601.4,602.0)))`; start 10.5, end 12.0 gives `(610.0,611.0)`; empty text gives None. **`test_conf`**: 0.0 gives 1.0, -inf and NaN give 0.0. **`test_load_failure_is_model_load_error`**: patched `fetch_pin` returns an empty `tmp_path`; the message starts `cannot load Systran/faster-whisper-small@536b0662742c: RuntimeError`. **`test_transcribe_with_stub_model`**: `faster_whisper.WhisperModel` patched to a stub returning one segment per chunk for chunks at 0.0 and 600.0, `ctranslate2.set_random_seed` to a recorder: the stub saw `TRANSCRIBE_KWARGS` exactly, the seed was set to 0 before each of the 2 calls, and starts are offset by 600.0 |
| 15 | Contract: Silero | `... tests/contract/test_vad.py` | `7 passed` (fake 3 + 1 fake-only, silero 3) |
| 16 | Contract: faster-whisper is model-only | `uv run pytest tests/contract/test_asr.py -q -m "not model"` | `5 passed, 5 deselected` |
| 17 | Smoke: real decode, Silero, fakes (local, Q5) | `... tests/smoke/test_audio_stage.py` | `4 passed`. **`test_low_speech_fixture`** silence.mp4: `[]`, sink `[AssetWarning(LOW_SPEECH, "audio stream 1: VAD found no speech in 4.0 s")]`, `asr.calls == []`. **`test_speech_fixture[600.0]`**, **`[2.0]`**: `asr.calls == [1]`, 2 utterances within 0.02 of `(0.00,2.82)` and `(3.20,6.60)`, empty sink. **`test_av_mismatch_clamped`**: real `probe` and decode of av_mismatch.mp4 (`duration_s` 3.0), a VAD marking each chunk as speech, `ScriptedASR` returning one utterance from `piece.start_s` to `piece_end + 0.6`: the last `end_s` equals that piece's end (≤ 3.0) and an `AssetRecord` with the probed asset builds |
| 18 | Laptop gate | `uv run pytest -q -m "not gpu and not model"` | base passed + **34**, base deselected + **8**; no failed, error, skipped or xfailed. The PR states the base numbers |
| 19 | Gate | `make check`; `uv run pyright`; `uv run ruff format --check .`; `uv run ruff check .` | exit 0; `0 errors, 0 warnings, 0 informations`; formatted; `All checks passed!` |
| 20 | **models: real ASR** | the `models` job | 8 E3 tests pass: 5 contract (`faster-whisper`) + 3 in `tests/smoke/test_asr_models.py`, with one module-scoped `FasterWhisperASR(Config())` (small, int8, CPU) and `SileroVAD`. **`test_low_speech_real`** silence.mp4: as row 17, and a counting wrapper sees 0 `transcribe` calls. **`test_speech_wer`**: speech.mp4 at default config gives `wer(transcript, " ".join(u.text for u in out)) <= 0.20` (at most 3 of 15 words wrong), every `u.lang == "en"`, empty sink, and a second run gives identical utterances; logs `speech.mp4 WER chunk_s=600: <x.xxx>`. **`test_speech_wer_small_chunks`**: `batch_seconds=2.0` gives WER ≤ 0.20 (M1 R8); logs `speech.mp4 WER chunk_s=2.0: <x.xxx>` |
| 21 | Card edits | `grep -c 'storage hosts under \*.hf.co' src/tapesift/cli/doctor.py`; `uv run pytest tests/unit/test_doctor.py -q`; `grep -c 'and under 60 s of speech in total' docs/spec.md` | `1`; all passed; `1` |
| 22 | Workflow | `grep -c 'continue-on-error' .github/workflows/models.yml`; `git diff --quiet main -- .github/workflows/ci.yml; echo $?` | `0`; `0` |
| 23 | Paths | `git diff --name-only main...HEAD` | exactly the 17 paths below |

**Test count, stated once.** Local: `test_audio_stage.py` 2 + 5 + 1 + 1 + 2 + 1 + 1 + 2 + 1 + 1 + 3 + 1 = **21**; `test_wer.py` **2**; `test_audio_faster_whisper.py` **4**; contract silero **3**; smoke **4**. Total **34**. Model: **8**, in the `models` job only.

```text
.github/workflows/models.yml
CHANGELOG.md
docs/spec.md
src/tapesift/audio/faster_whisper.py
src/tapesift/audio/phantoms.py
src/tapesift/audio/stage.py
src/tapesift/audio/vad.py
src/tapesift/cli/doctor.py
src/tapesift/eval/__init__.py
src/tapesift/eval/wer.py
tests/contract/test_asr.py
tests/contract/test_vad.py
tests/smoke/test_asr_models.py
tests/smoke/test_audio_stage.py
tests/unit/test_audio_faster_whisper.py
tests/unit/test_audio_stage.py
tests/unit/test_wer.py
```

**PR Numbers section:** the two WERs (row 20), the `models` job wall time cold and warm and the cache size, row 12's three peaks.

## Out of scope
- Real models on the laptop (ADR 0008).
- Long-form, accented or LibriSpeech WER; Whisper's `EnglishTextNormalizer` for published numbers (V2).
- `provenance` and the record (E7), the JSON mapping (E5), batched ASR across files (C5), GPU runs.
- Forcing `language="en"` (ADR 0010 keeps the detected language per utterance; determinism comes from the per-call seed).
- `no_speech_prob` in the phantom rule (needs an M1 change to `Utterance`).
- New config keys (`MAX_CARRY_S`, VAD options, the speech floor): M1 owns `config.py`.
- Making `models` a required check (the owner's action after 3 greens, Q4).

## Later (cut for the MVP demo)
- **Quietest-frame seam fallback** (r2's `quietest_cut`, rows 4, 12b and 14): when a buffer longer than 30 s has no VAD gap, cut at the lowest-RMS 50 ms frame instead of the buffer end. Add if the demo or V2 shows split words at seams.
- **Host audit test** (r2 row 31): audit-hook `socket.getaddrinfo` during a cold `tiny` fetch and assert every host is `huggingface.co` or `*.hf.co`, then an offline rerun prints `[]`. Belongs with Y3's offline CI run.
- **Third-party phantom data** (card 2 A, 13 phrases from the ICASSP 2025 Bag of Hallucinations, MIT + CC BY): grow the list by card if V2 finds phantoms outside the 3 in more than 1% of utterances.
- **Nightly `models` run** and a job-level path `if:` (needed only when `models` becomes a required check).
- The pre-approval WER experiment branch (card 4 A).
- Extra unit cases from r2 (run-break pieces, pass-count mismatch, piece-plan, nonzero audio start, multi-audio track smoke, Silero rate check, the music.m4a smoke).

## Risks
- **WER is unmeasured until the first `models` run.** The bound allows 3 of 15 wrong. If row 20 fails, stop and report the hypothesis and the normalized diff; the lead decides the bound or the default model by card. Never loosen it silently.
- **VAD separation** is 1.000 against 0.000 today. A Silero or onnxruntime upgrade that moves it fails rows 17 and 20 (the issue's stop condition).
- **Tone fixtures get `LOW_SPEECH`** (every tone fixture measures 0.000). The manifest's `warning_codes` are probe-level; E5 and E7 tests comparing codes must expect `LOW_SPEECH` on tone-only audio. The demo should use a real talk or speech.mp4, not clean.mp4.
- **Hard seam cut** (rule 4) on 30 s+ of gapless speech may split one word per seam. `ponytail:` comment in `seam_cut`.
- **Chunk-start VAD artifacts** (0.056 s measured) are absorbed by `SPAN_JOIN_S`.
- **Two decode passes.** AAC decodes at hundreds of times real time; revisit if C1 shows decode cost matters.
- **Real-model memory** is above the stage bound (Silero padding about 2.2 × 38.4 MB; faster-whisper's STFT about 100 MB for a 630 s piece): expect a 200-250 MB process peak.
- **Seeding is process-global.** v0.1's runner is single-process; S1 must keep calls serialized per process.
- **pyright strict on untyped faster-whisper:** targeted `reportMissingTypeStubs` ignores and `cast`s only.
- **`filterwarnings = error`.** Fix any new deprecation; never filter one without a card.
- **CI minutes while private.** Every non-docs PR runs `models` (about 5-15 min warm, more cold: about 0.5 GB ASR + 1 GB VLM + 0.13 GB embedder on a cold cache). If the Actions quota runs low, switch the trigger to `workflow_dispatch` only (T1) and tell the owner.

## T1 calls (list them in the PR)
1. Two decode passes (S1), with a WARNING on a sample-count mismatch.
2. Seams cut in VAD silence and carry the tail (S2): `MAX_CARRY_S` 30, `MIN_PIECE_S` 1.0, `SPAN_JOIN_S` 0.3; hard cut when no gap; the carry is always a copy.
3. Pieces with no VAD speech are never sent; flushed carries are sent at any length.
4. Silero options: threshold 0.5, minimum silence 500 ms, padding 200 ms; 16 kHz only.
5. Phantoms: whole-utterance match and VAD coverage ≤ 0.5; dropped before the overlap cap; one INFO line with counts.
6. `conf = exp(avg_logprob)`, capped at 1, 0 when not finite.
7. `LOW_SPEECH` whenever VAD speech is zero (threshold 0 included) and when nothing was decoded.
8. An out-of-range `asr.audio_track` falls back to the default track with one WARNING.
9. Pass-2 decoder warnings forwarded only if new.
10. Our own small normalizer, not Whisper's (V2 decides).
11. faster-whisper: language auto, word timestamps on, `vad_filter` off, `set_random_seed(0)` per call; CUDA only for gpu and server profiles.
12. One `models.yml` job: all `model` tests, `--all-extras`, one cache keyed on every pin, `paths-ignore` for docs, `timeout-minutes: 45`.
13. Overlap capping reuses `clamp_utterance`.

## Decision cards
All decided (table at the top). r2 reasoning, summarised:

### Card 1 (T3, privacy): model downloads contact `*.hf.co` hosts. Decided A (text), test deferred.
Options were A (say so in `doctor`, enforce in the models job), B (leave the text; a false privacy statement ships), C (`HF_HUB_DISABLE_XET=1`; edits M1's `hub.py` and the HTTP path still redirects to `*.hf.co`). Listing exact host names was rejected: HF rotates CDN hosts.

### Card 2 (T3, licensing): phantom list source. Decided C.
Options were A (13 sourced phrases with MIT and CC BY attribution), B (all 294 BoH rows; includes ordinary speech), C (the spec's own 3). C ships no third-party data. Would change it: V2 data showing phantoms outside the list in more than 1% of utterances.

### Card 3 (T2): 60 s speech floor on `LOW_SPEECH`. Decided A.
A 3-hour recording with 8 minutes of talk (ratio 0.044) keeps its transcript. Up to 60 s of VAD false positives may reach ASR; the no-speech-piece skip and the phantom filter limit the damage. Make it a config key only if a user needs to tune it.

### Card 4 (T2, CI minutes): measure WER before approval. Decided C.
The first `models` run on E3's draft PR measures it; the stop rule applies.
