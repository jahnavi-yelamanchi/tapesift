# 29. LanceDB store, text embeddings, `tapesift search`, and the search API for the web UI (E6)

Issue: #29   Lane: Core   Status: draft r3 (lean mode). Every card is decided (below); ready for the lead to approve.
Revisions: 2026-10-20 r3, lean mode (owner, 2026-10-20: working MVP demo first; opus decides, sonnet builds). r2's interrupted revision is folded in. Tests cut from 69 local to 31; `open_index` and `search_index` added for the web UI (docs/specs/40-web-ui.md, in parallel).

Planned against the merged M1 interfaces (`docs/specs/25-m1-interfaces.md`, on main at 7bcb1ee). M1 names used exactly as defined: `Store`, `Embedder`, `Hit`, `Modality`, `AssetRecord`, `Utterance`, `Caption`, `Provenance`, `Config`, `ConfigError`, `ModelLoadError`, `load_config`, `EMBEDDER`, `ModelPin`, `hub.fetch_pin`, `FakeEmbedder`, `MemoryStore`, and the contract fixtures `backend` and `store` (zero-argument factories). No name comes from an unapproved spec. E7 (#30, approved) calls E6: `LanceStore(cfg, OnnxEmbedder(cfg))` and `StoreError` (exit 2). If a merged name differs, stop and raise a card.

**Where the issue and M1 differ, M1 wins.** The issue says `store/embed.py`; M1 puts `OnnxEmbedder` in `src/tapesift/vision/embed.py`.

## Decisions (opus, 2026-10-20, lean mode; owner delegated)
| Card | Choice | Why |
| --- | --- | --- |
| 1 (T3) table schema and versioning | **A**: one `passages` table, schema metadata `tapesift.store_format = "1"` and `tapesift.embedder`; mismatch refused with `StoreError`, no migration | Stops silent mixing of vector spaces; costs one check at open |
| 2 (T3) `--out DIR` on `search` | **A**: add it; edit spec line 218 | `index --out x` then `search --out x` is the demo flow; without it users need a config file |
| 3 (T3) human output | **A**: quoted, escaped, 2-3 lines per hit, plain `typer.echo`; declared not machine-stable | Safe against terminal escape injection from media text; scripts and the UI use `--json` / the Python API |
| 4 (T2) flat search, no ANN | **A** | Exact and deterministic; 500k rows in under 0.4 s measured |
| 5 (T2) no near-duplicate collapsing | **A** | Matches M1 and `MemoryStore`; revisit if the demo shows duplicates crowding top 5 |
| 6 (T2) `StoreError`, exit 2 in both CLIs | **A** | Already in approved E7 (30-runner.md) |
| 7 (T2) one writer, no lock | **A** | E7 has one writer per run; the UI only reads |
| new T1 | `search_index` / `open_index` in `store/lance.py` for the UI | The UI needs a plain function; the CLI uses the same path, so one code path is tested |
| new T1 | `read_consistency_interval=timedelta(0)` on connect | A long-lived UI process must see rows a later `tapesift index` adds |
| new T1 | `lance-fake` contract param builds its folder with `tempfile.mkdtemp()` | The merged `store` fixture calls `factory()` with no `tmp_path`; this avoids editing the fixture body |

Nothing here spends money or touches credentials.

## Goal
After this lands:
- `tapesift.vision.embed.OnnxEmbedder` implements M1's `Embedder` with the pinned `BAAI/bge-small-en-v1.5` ONNX model on CPU (onnxruntime and tokenizers, no torch).
- `tapesift.store.lance.LanceStore` implements M1's `Store` on embedded LanceDB in `out_dir/store/`: exact (flat) cosine search, M1's filters and tie order.
- `tapesift.store.lance.search_index(query, out_dir, ...) -> list[Hit]` is the plain Python search call the web UI uses. Each `Hit` has `asset_id`, `path` (absolute media path), `start_s`, `end_s` (seconds on the media clock), `modality`, `text`, `media_text`, `score`, `trust`.
- `tapesift search "query" [--config FILE] [--out DIR] [--k N] [--modality speech|visual|any] [--asset ID] [--json]` prints ranked hits: human text on stdout, or M1 card 3's `{"query", "hits"}` with `--json`. Exit codes per spec 212.

Done when golden queries on fixtures return the expected IDs, with `FakeEmbedder` on the laptop and the real embedder in the `models` CI job.

## Read first
- `docs/specs/25-m1-interfaces.md`: card 3 (`Hit`, `{"query", "hits"}`, `trust`), card 8 (`embed_text(texts, *, kind)`, truncation, bge's query prefix), card 4 and R7 (`--config`, `out_dir`), R4 (`fetch_pin`), R5, R6 (lazy imports); `store/types.py`, `vision/types.py` (docstrings are the contract); the fakes and contract tables.
- `docs/specs/30-runner.md`: `pipeline.index.open_store`, `delete` on a changed file, `StoreError` exit 2, absolute `asset.path` (card 5), the two registration lines in `cli/__init__.py`.
- docs/spec.md: 42, 146, 212, 218, 340, 432, 513 (Y1), Y3, 732-745.
- Code: `src/tapesift/cli/__init__.py` (`ExitCode`, `app`, `JsonOption`), `src/tapesift/schema/records.py` (`Hit`), `src/tapesift/config.py`, `tests/contract/test_store.py` and `test_embedder.py` (fixture form), `tests/smoke/conftest.py`, `tests/fixtures/manifest.json`, `scripts/make_fixtures.py` (`BURNED_TEXT`).
- **Observed by the planner, 2026-10-20** (scratch venv, `lancedb==0.40.0`, pyarrow 26.0.0, numpy 2.5.4, Python 3.12; no weights):
  - `lancedb.connect(path)` creates the folder at once, parents included. So the "no index" check runs before any connect.
  - `db.open_table("passages")` on a missing table raises `ValueError`. Use `TABLE in db.list_tables().tables`.
  - Schema metadata from `pa.schema(..., metadata=...)` persists and comes back as `dict[bytes, bytes]`.
  - `distance_type("cosine")` gives `_distance = 1 - similarity`; identical unit vectors give `-1.19e-07`, so clamp `1 - d`.
  - SQL filters: single quotes double (`'a''b'` matches `a'b`).
  - `limit(None)` raises; pass an explicit limit.
  - **Ties:** identical vectors come back in insertion order, not by asset id. `distance_range(None, upper)` is exclusive and compares in float32: use `np.nextafter(np.float32(d_k), np.float32(2))`.
  - Flat search, dim 384, k = 10, M3 Pro: 10k rows 6-11 ms, 100k 60-99 ms, 500k 121-357 ms, filters included. Fragment count (one per upsert) did not slow search.
  - Two processes writing one table: no error, correct final rows (v0.1 doesn't rely on it).
  - `python -W error`: lancedb import, create, add, search, delete raise no warning.
  - pyright strict: bind `pa: Any = importlib.import_module("pyarrow")` and `lancedb` as `Any`, cast at the boundary: 0 errors, no `# type: ignore`.
  - Network: no telemetry in lancedb 0.40.0; cloud hosts only for `db://` URIs.
  - bge-small-en-v1.5 at `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` (config files only): CLS pooling, hidden 384, max 512 positions, `pad_token_id` 0, lowercase tokenizer, query instruction `Represent this sentence for searching relevant passages: ` (trailing space), `onnx/model.onnx` 133,093,490 bytes. Not verified without weights: ONNX input/output names (usual export: `input_ids`, `attention_mask`, `token_type_ids` in, `last_hidden_state` out). The loader checks them; the `models` job verifies.
  - FakeEmbedder scores on the golden records: "quarterly pricing review" scores 0.654654 against speech.mp4's first sentence and 0.0 elsewhere; "ignore previous instructions" scores 0.577350 against each burned_text.mp4 caption row and 0.0 elsewhere.

## Scope
May change:
- New: `src/tapesift/vision/embed.py`, `src/tapesift/store/lance.py`, `src/tapesift/cli/search.py`.
- `src/tapesift/cli/__init__.py`: two lines after `doctor` and before `def main()`:
  ```python
  from tapesift.cli.search import search  # noqa: E402  (needs ExitCode, app and JsonOption above)
  app.command()(search)
  ```
  E7 adds its own pair at the same place; whichever merges second keeps both, `index` before `search`.
- `tests/contract/test_store.py`: one `pytest.param(_lance_fake, id="lance-fake")` in the `store` fixture's params, where `_lance_fake()` returns `LanceStore(Config(out_dir=Path(tempfile.mkdtemp())), FakeEmbedder())`, plus the imports it needs. The fixture body is unchanged.
- `tests/contract/test_embedder.py`: one `pytest.param(lambda: OnnxEmbedder(Config()), id="onnx", marks=pytest.mark.model)`, plus its import.
- New tests: `tests/unit/test_store_lance.py`, `tests/unit/test_embed_onnx.py`, `tests/unit/test_search_cli.py`, `tests/smoke/test_search_golden.py`.
- `docs/spec.md`: line 218 only (card 2).
- `CHANGELOG.md`: one line under Unreleased, Added: ``- `tapesift search` and `tapesift.store.lance.search_index`: ranked speech and caption moments from a LanceDB index in `out_dir/store/`, embedded on CPU with bge-small-en-v1.5 (ONNX); on-screen words stay in `media_text` and every hit is tagged `untrusted_media` (#29).``

Must not touch:
- M1's files: `src/tapesift/store/types.py`, `src/tapesift/vision/types.py`, `src/tapesift/schema/**`, `src/tapesift/config.py`, `src/tapesift/hub.py`, `tests/fakes.py`, contract test bodies.
- `pyproject.toml`, `uv.lock`, `THIRD_PARTY.md` (M1 added the deps and the bge row).
- `src/tapesift/{runner,pipeline,audio,media}/**`, `src/tapesift/cli/index.py`, `src/tapesift/cli/doctor.py`, the rest of `src/tapesift/vision/**`, `src/tapesift/warning_codes.py`.
- `tests/fixtures/**`, `scripts/**`, `.github/**` (E3's `models.yml` already runs every `model`-marked test), `Makefile`, `README.md`, `AGENTS.md`, `CLAUDE.md`, the web UI's paths.

## Interfaces touched
Before: M1's Protocols only. After: the three modules below. Docstrings are part of the contract.

### `src/tapesift/vision/embed.py`
```python
"""E6: M1's text Embedder on the pinned bge-small-en-v1.5, ONNX on CPU (onnxruntime + tokenizers,
no torch). Loads only EMBEDDER.files through hub.fetch_pin (R4). Imported lazily (R6)."""

QUERY_PREFIX: Final = "Represent this sentence for searching relevant passages: "  # bge model card
MAX_TOKENS: Final = 512  # prefix and [CLS]/[SEP] included (card 8: truncate)
BATCH_SIZE: Final = 32
DIM: Final = 384
MODEL_INPUTS: Final = ("input_ids", "attention_mask", "token_type_ids")


class OnnxEmbedder:
    """bge-small-en-v1.5: CLS pooling, then L2 normalization. kind="query" prepends QUERY_PREFIX."""

    def __init__(self, cfg: Config) -> None: ...  # cfg unused in v0.1
    @property
    def id(self) -> str: ...  # EMBEDDER.id
    @property
    def dim(self) -> int: ...  # DIM
    def embed_text(
        self, texts: Sequence[str], *, kind: Literal["query", "passage"]
    ) -> NDArray[np.float32]: ...
```
- **Loading.** `d = tapesift.hub.fetch_pin(EMBEDDER)` through the module attribute (tests patch it); its `ModelLoadError` propagates. Then in one `try`: `tok = tokenizers.Tokenizer.from_file(str(d / "tokenizer.json"))`, `tok.enable_truncation(MAX_TOKENS)`, `tok.enable_padding(pad_id=0, pad_token="[PAD]")`; `session = onnxruntime.InferenceSession(str(d / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"])` through the module attribute. Any `Exception` becomes `ModelLoadError(f"cannot load {EMBEDDER.repo}@{EMBEDDER.revision[:12]}: {type(e).__name__}: {e}")`.
- **Checks after loading** (same prefix, `ModelLoadError`): input names must be a subset of `MODEL_INPUTS` containing `input_ids` (else `unexpected model inputs {names}`); the first output's last dimension must be `DIM` (else `output width {w}, expected 384`).
- **`embed_text`.** Unknown `kind` raises `ValueError`. `[]` gives `np.empty((0, DIM), np.float32)` without running the session. Otherwise per slice of `BATCH_SIZE`: `tok.encode_batch([prefix + t for t in batch])` (`prefix` is `QUERY_PREFIX` for queries, `""` for passages); feed exactly the declared input names as `np.int64` (batch, longest) from `ids`, `attention_mask`, `type_ids`; `hidden = session.run(None, feed)[0]`; `cls = hidden[:, 0, :]` as float32; rows `cls / np.maximum(np.linalg.norm(cls, axis=1, keepdims=True), 1e-12)`. Result: one C-contiguous float32 array (len(texts), DIM), input order.
- **Typing.** If onnxruntime is untyped under pyright strict, bind it as `Any` via `importlib.import_module` and cast at the boundary. No `# type: ignore`.

### `src/tapesift/store/lance.py`
```python
"""E6: M1's Store on embedded LanceDB in out_dir / "store" (spec D5), plus the search API the CLI
and the web UI share. One row per utterance (SPEECH) and per caption (VISUAL); exact (flat) cosine
search, no ANN index (card 4). Schema metadata records the store format and the embedder id; any
other value is refused, never migrated (card 1). One writer at a time (card 7)."""

STORE_DIR: Final = "store"
TABLE: Final = "passages"
STORE_FORMAT: Final = "1"  # bump on any change to the columns, their meaning or the passage text
FORMAT_KEY: Final = "tapesift.store_format"
EMBEDDER_KEY: Final = "tapesift.embedder"


class StoreError(RuntimeError):
    """The index under out_dir can't be used: missing, not a tapesift store, another store
    format, another embedder, or it can't be opened. CLIs exit 2 (card 6)."""


class LanceStore:
    def __init__(self, cfg: Config, embedder: Embedder) -> None: ...
    def upsert(self, record: AssetRecord) -> None: ...
    def delete(self, asset_id: str) -> None: ...
    def search(
        self, query: str, k: int = 10, *, modality: Modality | None = None, asset_id: str | None = None
    ) -> list[Hit]: ...


def load_embedder() -> Embedder:
    """OnnxEmbedder(Config()), imported here (R6). Tests patch this module attribute."""


def open_index(out_dir: Path) -> LanceStore:
    """An existing index, opened for searching. In order:
    1. (out_dir / STORE_DIR) is not a folder: StoreError(f'no index at {out_dir}: run "tapesift
       index" first, or pass --out'). Nothing is created and no model loads.
    2. embedder = load_embedder()  (ModelLoadError propagates)
    3. LanceStore(Config(out_dir=out_dir), embedder)  (StoreError on another format or embedder)"""


def search_index(
    query: str,
    out_dir: Path,
    *,
    k: int = 10,
    modality: Modality | None = None,
    asset_id: str | None = None,
) -> list[Hit]:
    """The web UI's search call. Opens the index once per process per out_dir (cached, so the
    model loads once) and returns open_index(out_dir).search(query, k, modality=..., asset_id=...).
    Hits: score descending, ties by (asset_id, start_s). Hit.path is the absolute media path E7
    recorded; start_s/end_s are seconds on the media clock (seek a player there); end_s == start_s
    for VISUAL. Every text field is untrusted media content (Hit.trust): render it as text, never
    as HTML. Sees rows a later `tapesift index` adds. Raises StoreError, ModelLoadError, or
    ValueError (k < 1). Failed opens are not cached."""
```
`search_index` calls `_open_cached(Path(os.path.abspath(out_dir)))`, where `_open_cached = functools.cache(open_index)`. Tests reset it with `_open_cached.cache_clear()`. `ponytail:` comment: unbounded per-process cache, one entry per out_dir; two threads racing the first call may both load the model (harmless).

**Table `passages`** (card 1), columns in order, all non-null:

| Column | Arrow type | SPEECH row (per `Utterance`) | VISUAL row (per `Caption`) |
| --- | --- | --- | --- |
| `asset_id` | `string` | `record.asset.id` | same |
| `path` | `string` | `str(record.asset.path)` | same |
| `modality` | `string` | `"speech"` | `"visual"` |
| `start_s` | `float64` | `u.start_s` | `c.t_s` |
| `end_s` | `float64` | `u.end_s` | `c.t_s` |
| `text` | `string` | `u.text` | `c.text` |
| `media_text` | `list<string>` | `[]` | `list(c.media_text)` |
| `vector` | `fixed_size_list<float32>[embedder.dim]` | `embed(u.text)` | `embed(" ".join((c.text, *c.media_text)))` |

Schema metadata `{FORMAT_KEY: STORE_FORMAT, EMBEDDER_KEY: embedder.id}`, built with `pa.schema([pa.field(name, type, nullable=False), ...], metadata=...)`. No chunking beyond M1's one row per utterance and per caption; long text is truncated by the embedder.

Behaviour:
- **`__init__`.** `self._dir = cfg.out_dir / STORE_DIR`; `self._db = lancedb.connect(self._dir, read_consistency_interval=timedelta(0))` (so a long-lived reader sees later commits; if lancedb 0.40 lacks the argument, call `table.checkout_latest()` at the start of each `search` instead, T1). Then `self._open_table()`. Any `Exception` other than `StoreError` while connecting, listing or opening becomes `StoreError(f"{self._dir}: cannot open the store: {type(e).__name__}: {e}")`.
- **`_open_table()`.** If `TABLE` is in `self._db.list_tables().tables`, open it and check metadata (bytes decoded `"utf-8", "replace"`), else `self._table = None`:
  1. no `FORMAT_KEY`: `StoreError(f"{self._dir}: not a tapesift store (no {FORMAT_KEY} metadata); index into a new --out")`;
  2. another format `f`: `StoreError(f"{self._dir}: unsupported store format {f!r} (this tapesift reads {STORE_FORMAT!r}); index into a new --out")`;
  3. another embedder `e` (missing is `""`): `StoreError(f"{self._dir}: indexed with {e}, but this tapesift embeds with {embedder.id}; index into a new --out")`.
- **`upsert(record)`.** Build texts (SPEECH rows in utterance order, then VISUAL rows in caption order). `vectors = embedder.embed_text(texts, kind="passage")`, one call, only when non-empty; a shape other than `(len(texts), embedder.dim)` raises `ValueError`. Embedding comes first, so an embedder failure leaves old rows untouched. Create the table if none exists. Then `delete(f"asset_id = {q(id)}")` and `add(rows)` when there are rows. `q(s) = "'" + s.replace("'", "''") + "'"` quotes every filter string. Idempotent.
- **`delete(asset_id)`.** No table: no-op. Else `delete(f"asset_id = {q(asset_id)}")`.
- **`search(query, k, *, modality, asset_id)`.**
  1. `k < 1`: `ValueError(f"k must be >= 1, got {k}")`.
  2. If `self._table is None`, call `self._open_table()` again (a reader opened before the first upsert). Still none: `[]`.
  3. `where`: `" AND ".join` of `f"modality = {q(modality.value)}"` and `f"asset_id = {q(asset_id)}"` for the filters given, or None.
  4. `n = table.count_rows(where)`; `n == 0`: `[]` without embedding.
  5. `v = embedder.embed_text([query], kind="query")[0]`. Base: `table.search(v, vector_column_name="vector").distance_type("cosine").select([the 7 non-vector columns])`, plus `.where(where, prefilter=True)` when set.
  6. Pass 1: `rows = base.limit(min(k, n)).to_list()`.
  7. Ties at the cut: if `len(rows) == k < n`, `d_k = max(r["_distance"] for r in rows)`, then `rows = base.distance_range(None, float(np.nextafter(np.float32(d_k), np.float32(2.0)))).limit(n).to_list()`.
  8. Each row becomes `Hit(asset_id, path, start_s, end_s, Modality(modality), text, tuple(media_text), score)` with `score = min(1.0, max(-1.0, 1.0 - _distance))` as a builtin `float`.
  9. Sort by `(-score, asset_id, start_s, modality, end_s, text)`; return the first `k`.
- No near-duplicate collapsing (card 5), no ANN index (card 4, `ponytail:` comment: ceiling about 1M rows; upgrade: IVF index behind a row-count threshold), no compaction (Risks).

### `src/tapesift/cli/search.py`
```python
"""`tapesift search`: search the index in out_dir/store/ and print hits (M1 card 3). Reads only.
tapesift.store.lance is imported inside the command (R6)."""

ASSET_ID_RE: Final = re.compile(r"(?:tsid1|sha256):[0-9a-f]{64}")  # ADR 0012; fullmatch


class ModalityChoice(StrEnum):
    SPEECH = "speech"
    VISUAL = "visual"
    ANY = "any"  # modality=None


def render(query: str, hits: Sequence[Hit]) -> str: ...  # human output, no trailing newline


def search(
    query: Annotated[str, typer.Argument(help="What to look for, in plain words.")],
    config: Annotated[Path | None, typer.Option("--config", help="Config file (default ./tapesift.toml).")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Index folder, as given to tapesift index --out.")] = None,
    k: Annotated[int, typer.Option("--k", min=1, help="Number of results.")] = 10,
    modality: Annotated[ModalityChoice, typer.Option("--modality", help="speech, visual or any.")] = ModalityChoice.ANY,
    asset: Annotated[str | None, typer.Option("--asset", help="Only this asset ID.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Search indexed speech and captions; prints ranked moments with timestamps."""
```
Flow. Errors go to stderr as `error: <message>`.
1. `query.strip() == ""`: `typer.BadParameter("must not be empty", param_hint="QUERY")`, exit 2.
2. `asset` set and not `ASSET_ID_RE.fullmatch(asset)`: `typer.BadParameter("not an asset ID (tsid1:<64 hex> or sha256:<64 hex>)", param_hint="--asset")`, exit 2. A well-formed unknown ID gives no hits, exit 0.
3. `cfg = load_config(config, out_dir=out)`; `ConfigError`: exit 2.
4. `idx = lance.open_index(cfg.out_dir)` (uncached; the CLI is one query). `StoreError`: exit 2. `ModelLoadError`: exit 3.
5. `hits = idx.search(query, k, modality=None if modality is ModalityChoice.ANY else Modality(modality.value), asset_id=asset)`.
6. Exit 0, zero hits included. `--json`: `json.dumps({"query": query, "hits": [dataclasses.asdict(h) for h in hits]}, ensure_ascii=False, indent=2)`, `query` as given. Otherwise `render(query, hits)`.

**`render`** (card 3), lines joined by `"\n"`:
- No hits: exactly `f"no results for {qt(query)}"`.
- Else the header `f"{n} result{'' if n == 1 else 's'} for {qt(query)} (text from media; untrusted)"`, then per hit `i` from 1:
  - `f"{i}  {h.score:.3f}  {h.modality.value}  {when}  {qt(h.path)}  {h.asset_id}"`, with `when = f"{hms(h.start_s)}-{hms(h.end_s)}"` for SPEECH and `hms(h.start_s)` for VISUAL;
  - `f"   text: {qt(h.text)}"`;
  - when `h.media_text`: `f"   on-screen: {', '.join(qt(m) for m in h.media_text)}"`.
- `qt(s)`: `"` + `s` with `\` and `"` backslash-escaped and every `c` with `not c.isprintable()` written as `\uXXXX` (or `\UXXXXXXXX` above U+FFFF) + `"`.
- `hms(t)`: `cs = math.floor(t * 100 + 0.5)`, then `f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"`.
- Printed with `typer.echo`, never rich.

### docs/spec.md edit (line 218; card 2)
`tapesift search "query" [--config FILE] [--k 10]` becomes `tapesift search "query" [--config FILE] [--out DIR] [--k 10]`. Nothing else on the line changes.

## Acceptance
**Baseline.** The builder runs `uv run pytest -q -m "not gpu and not model"` on its base commit and states `B passed, D deselected` in the PR.

**Records.** `Z = "0" * 40`. `prov(asr, vlm)` is `Provenance(__version__, "fake:asr@" + Z if asr else None, "fake:vlm@" + Z if vlm else None, "caption_v1" if vlm else None)`.
- Unit: `A` is `"tsid1:" + "a" * 64` at `Path("/media/talk.mp4")`, duration 10.0, utterances `(1.5, 4.25, "The quarterly pricing review starts at nine.")` and `(5.0, 8.0, "Revenue grew twelve percent while costs stayed flat.")` (lang `"en"`, conf 1.0, no words). `B` is `"tsid1:" + "b" * 64` at `Path("/media/slides.mp4")`, duration 100.0, captions `Caption(62.0, "a slide", 1.0, ("BUY NOW",))` and `Caption(63.0, "a chart", None, ())`.
- Golden smoke, built with E1's `probe`: **S** = speech.mp4 with utterances `(0.0, 2.82, s1)` and `(3.2, 6.6, s2)` (`s1, s2 = re.split(r"(?<=\.) ", manifest transcript)`) and captions `Caption(float(t), f"fake caption {w}x{h}", 1.0, ())` for t in 0..6; **Bt** = burned_text.mp4, no utterances, captions at 0.0, 1.0, 2.0 with `media_text=(BURNED_TEXT,)`; **C** = clean.mp4, captions 0.0-4.0. Upserted once per module and embedder.

### `tests/unit/test_store_lance.py`: 13 tests (`FakeEmbedder()`, `tmp_path`)
| Test | Asserts |
| --- | --- |
| `test_table_schema_exact` | After upserting A: the 8 columns in order, all non-null, `vector` `fixed_size_list<float32>[256]`, metadata exactly `{b"tapesift.store_format": b"1", b"tapesift.embedder": b"fake:embedder@" + Z}` |
| `test_passage_texts_and_kind` | A spy embedder: upserting B is one call, `kind="passage"`, texts `["a slide BUY NOW", "a chart"]`; a search adds one `kind="query"` call with `[query]` |
| `test_embed_failure_keeps_old_rows` | After A, an embedder raising `RuntimeError("embed")`: `upsert(A2)` raises it and A's 2 rows are still found |
| `test_reopen_sees_rows` | A new `LanceStore` on the same `out_dir` finds A at rank 1 for "quarterly pricing review" |
| `test_search_is_read_only` | `{relative path: (size, st_mtime_ns)}` under `out` is unchanged by a new `LanceStore` plus 3 searches (no filter, `modality=VISUAL`, `asset_id=A.id`) |
| `test_embedder_mismatch_refused` | A `FakeEmbedder` subclass with id `"fake:other@" + Z` on a fake-built store: `StoreError` with exactly the card 1 item 3 message |
| `test_other_format_refused` | A test-made `passages` table with format `"2"`: the item 2 message; one with no metadata: message ends `"(no tapesift.store_format metadata); index into a new --out"` |
| `test_ties_cut_by_asset_then_start` | Upsert `"tsid1:" + "f" * 64`, then `"tsid1:" + "0" * 64`, each with captions "same text" at 0.0 and 1.0: `k=1` gives (0-asset, 0.0); `k=3` gives (0, 0.0), (0, 1.0), (f, 0.0) |
| `test_quotes_in_ids_are_escaped` | Asset id `"x'y"` is found with `asset_id="x'y"`; `asset_id="x' OR '1'='1"` gives `[]`; `delete("x'y")` removes only its rows |
| `test_hit_fields_and_clamped_score` | "a chart" against B gives `score == 1.0` exactly; every hit has `type(score) is float`, `media_text` a tuple of str, `modality` a `Modality`, `trust == "untrusted_media"`, and `json.dumps(dataclasses.asdict(hit))` works |
| `test_open_index_missing_creates_nothing` | `open_index(tmp_path / "o")` raises `StoreError` with exactly `f'no index at {o}: run "tapesift index" first, or pass --out'`; `o` does not exist afterwards; the patched `load_embedder` was not called |
| `test_search_index_loads_model_once` | With `load_embedder` patched to a counting `FakeEmbedder` factory and the cache cleared: two `search_index("quarterly pricing review", out)` calls return equal `list[Hit]`s, `hits[0].path == "/media/talk.mp4"`, `(start_s, end_s) == (1.5, 4.25)`, and the factory ran once |
| `test_long_lived_index_sees_new_rows` | `LanceStore(Config(out_dir=out), FakeEmbedder())` creates an empty store folder (no table); `idx = open_index(out)` then returns `[]` for any query; a second `LanceStore` upserts A; `idx.search(...)` now finds A; that writer then upserts B; `idx.search("a chart", modality=VISUAL)` finds B |

### `tests/unit/test_embed_onnx.py`: 6 tests (stubs; no weights)
`tapesift.hub.fetch_pin` returns `tmp_path` holding an empty `onnx/model.onnx` and a test-built `tokenizer.json` (`WordLevel` over `[PAD]=0, [UNK]=1, [CLS]=2, [SEP]=3` plus the test's words, lowercase normalizer, `Whitespace` pre-tokenizer, `TemplateProcessing("[CLS] $A [SEP]")`). `onnxruntime.InferenceSession` is patched with a `StubSession` that records its arguments and feeds, declares the 3 `MODEL_INPUTS` and output shape `["batch", "seq", 384]` (both configurable), and returns `h` with `h[b, 0, :]` a deterministic bag-of-ids vector and `h[b, 1:, :] = 1e3` (any pooling but CLS fails).

| Test | Asserts |
| --- | --- |
| `test_id_dim_and_cls_pooling` | `id == "onnx:bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"`, `dim == 384`; rows equal the stub's CLS rows L2-normalized within 1e-6; built with `providers == ["CPUExecutionProvider"]` |
| `test_query_prefix_only_for_queries` | The recorded query row starts with `QUERY_PREFIX`'s tokens; the passage row of the same text does not |
| `test_truncates_to_512_tokens` | 5,000 words: the fed row has 512 ids ending in `[SEP]`; the output row has norm 1 within 1e-5 |
| `test_batches_of_32_in_order` | 70 texts: `run` batch sizes 32, 32, 6; shape `(70, 384)`; row `i` equals `embed_text([texts[i]], kind="passage")[0]` within 1e-6 |
| `test_load_errors_are_model_load_error[session]` | `InferenceSession` raising `RuntimeError("bad onnx")` gives exactly `"cannot load BAAI/bge-small-en-v1.5@5c38ec7c405e: RuntimeError: bad onnx"` |
| `test_load_errors_are_model_load_error[width]` | Output shape `[..., 256]` gives a message ending `"output width 256, expected 384"` |

### `tests/unit/test_search_cli.py`: 10 tests (`CliRunner`; LanceStore with `FakeEmbedder`)
Each test seeds `out` with A and B unless it says otherwise; `tapesift.store.lance.load_embedder` is patched to `FakeEmbedder`. `R(args)` is `runner.invoke(app, ["search", *args])`.

| Test | Asserts |
| --- | --- |
| `test_json_shape_exact` | `["quarterly pricing review", "--out", out, "--k", "2", "--json"]`: exit 0; keys exactly `["query", "hits"]`; each hit's keys exactly `["asset_id", "path", "start_s", "end_s", "modality", "text", "media_text", "score", "trust"]`; `hits[0]` is A, speech, 1.5-4.25, `media_text == []` |
| `test_human_output_exact` | `--k 4`: stdout is exactly the block below plus a newline |
| `test_human_output_escapes_untrusted_text` | A caption with media text `"\x1b[31mRED‮\nNEXT"`: stdout has no ESC, no U+202E and no extra line; it contains `on-screen: "\u001b[31mRED‮\u000aNEXT"` (backslashes literal) |
| `test_no_index_exits_2` | An empty `tmp_path / "o"`, with `load_embedder` raising: exit 2, stderr exactly `f'error: no index at {o}: run "tapesift index" first, or pass --out'`, `o / "store"` absent |
| `test_model_load_error_exits_3` | Seeded out, `load_embedder` raising `ModelLoadError("fake: no model")`: exit 3, stderr exactly `error: fake: no model` |
| `test_incompatible_index_exits_2` | `load_embedder` returning the `fake:other` embedder: exit 2, stderr `error: ` + the mismatch message |
| `test_config_and_out_flag` | `conf/t.toml` with `out_dir = "idx"`, seeded at `conf/idx`, run from another cwd with `--config`: A found (R7). Adding `--out <other seeded folder>`: hits come from that folder |
| `test_bad_arguments_exit_2` | Each exits 2: query `"   "`; `--asset nope` (stderr names `--asset`); `--k 0`; `--modality audio`. And `--asset "tsid1:" + "c" * 64` exits 0 with no hits |
| `test_modality_filter` | `--modality visual --k 100 --json`: at least one hit, all visual |
| `test_search_import_is_light` | `subprocess.run([sys.executable, "-c", "import sys, tapesift.cli.search; print(sorted({...} & set(sys.modules)))"], timeout=60)` with the R6 set plus `av` and `lancedb` prints `[]` |

`test_human_output_exact` expects:
```text
4 results for "quarterly pricing review" (text from media; untrusted)
1  0.655  speech  0:00:01.50-0:00:04.25  "/media/talk.mp4"  tsid1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
   text: "The quarterly pricing review starts at nine."
2  0.000  speech  0:00:05.00-0:00:08.00  "/media/talk.mp4"  tsid1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
   text: "Revenue grew twelve percent while costs stayed flat."
3  0.000  visual  0:01:02.00  "/media/slides.mp4"  tsid1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
   text: "a slide"
   on-screen: "BUY NOW"
4  0.000  visual  0:01:03.00  "/media/slides.mp4"  tsid1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
   text: "a chart"
```

### `tests/smoke/test_search_golden.py`: 4 collected; 2 local, 2 in the `models` job
Module fixture `golden`, params `pytest.param("fake", id="fake")` and `pytest.param("onnx", id="onnx", marks=pytest.mark.model)`, builds `out` from S, Bt and C with `FakeEmbedder()` or `OnnxEmbedder(Config())`, patches `load_embedder` to return it, and searches through the CLI with `--out out --json`.

| Test | Asserts |
| --- | --- |
| `test_golden_spoken_text_rank_one[<e>]` | "quarterly pricing review": `hits[0]` is S, speech, `start_s == 0.0`, `end_s == 2.82`, `text == s1`. fake: score `approx(0.654654, abs=1e-5)` |
| `test_golden_burned_text_rank_one[<e>]` | "ignore previous instructions": `hits[0]` is Bt, visual, `media_text == [BURNED_TEXT]`, `trust == "untrusted_media"`. fake: hits 0-2 are Bt at 0.0, 1.0, 2.0 in that order |

### Contract params (M1's tests; no new test code)
| Module | Param | Tests |
| --- | --- | --- |
| `tests/contract/test_store.py` | `lance-fake` | 15, local |
| `tests/contract/test_embedder.py` | `onnx`, marked `model` | 8, `models` job |

**Test count, stated once.** New local tests: 13 + 6 + 10 + 2 = **31**, plus 15 contract runs of `lance-fake`. `models` job: 2 + 8 = **10**.

### Commands
| Command | Expected |
| --- | --- |
| `uv run pytest tests/unit/test_store_lance.py tests/unit/test_embed_onnx.py tests/unit/test_search_cli.py -q` | `29 passed` |
| `uv run pytest tests/smoke/test_search_golden.py -q -m "not model"` | `2 passed, 2 deselected` |
| `uv run pytest tests/contract -q -m "not model"` | `52 passed, 8 deselected` on M1-only main (M1's 37 plus `lance-fake`'s 15); add other merged specs' contract params |
| `models` CI job (E3's `models.yml`, runs every `model` test) | the 10 E6 tests pass. Never on the laptop (ADR 0008) |
| `uv run pytest -q -m "not gpu and not model"` | `B + 46 passed`, `D + 10 deselected`; no failed, error, skipped or xfailed |
| `uv run pyright`; `uv run ruff format --check .`; `uv run ruff check .` | `0 errors, 0 warnings, 0 informations`; clean; clean |
| `grep -rnE 'type: ignore\|pyright: ignore' src/tapesift/store/lance.py src/tapesift/vision/embed.py src/tapesift/cli/search.py` | no output |
| `grep -rnE 'snapshot_download\|hf_hub_download\|from_pretrained' src/tapesift/store src/tapesift/vision/embed.py` | no output (R4) |
| `uv run python -c "import sys, tapesift.cli; print(sorted({'torch','transformers','ctranslate2','faster_whisper','lancedb','pyarrow','onnxruntime','tokenizers','huggingface_hub','av'} & set(sys.modules)))"` | `[]` |
| `grep -c -F '[--config FILE] [--out DIR] [--k 10]' docs/spec.md` | `1` |
| `git diff --name-only main...HEAD` | exactly: `CHANGELOG.md`, `docs/spec.md`, `src/tapesift/cli/__init__.py`, `src/tapesift/cli/search.py`, `src/tapesift/store/lance.py`, `src/tapesift/vision/embed.py`, `tests/contract/test_embedder.py`, `tests/contract/test_store.py`, `tests/smoke/test_search_golden.py`, `tests/unit/test_embed_onnx.py`, `tests/unit/test_search_cli.py`, `tests/unit/test_store_lance.py` |
| `make check` | exits 0 |

## Out of scope
- The web UI itself (docs/specs/40-web-ui.md). E6 only provides `search_index` / `open_index`.
- Windowed chunking, keyword or hybrid ranking, reranking, score calibration, image embeddings (S3).
- Locking, migrations, `tapesift purge`, `serve`, `mcp`, GPU embedding, a `--profile` flag on `search`, several `out_dir`s at once.

## Later (cut for the MVP demo)
- `lance-onnx` contract param in the `models` job (golden + embedder contract cover the real path).
- The "unrelated query stays low" threshold test (needed a pinned real-score threshold).
- Unit tests that duplicated the `lance-fake` contract run (row count after re-upsert, empty-record clears rows, combined filters, k above row count) and the feeds-only-declared-inputs and empty-input embedder stubs.
- Near-duplicate collapsing (card 5), ANN index (card 4), compaction (`table.optimize`), single-commit upsert (`merge_insert`).

## Risks
- **Real embedder facts unverified on the laptop.** The loader checks input names and output width, so a mismatch is a loud `ModelLoadError`; the `models` job verifies; a fix is T1 inside `embed.py`.
- **E6's model tests need E3's `models.yml` on main.** Until then the PR stays draft with the 10 model tests collected but not run.
- **onnxruntime determinism.** M1's contract wants identical outputs for identical calls. If the `models` job shows drift, set `intra_op_num_threads = 1` (T1) and report the speed cost.
- **Upsert is two Lance commits** (delete, then add). A crash between them leaves the asset with no rows and no JSON (E7 writes JSON after the upsert), so the next run re-indexes it. `ponytail:` comment; upgrade: `merge_insert`.
- **Versions and fragments accumulate** per upsert; no measured slowdown at 1,000 fragments. `ponytail:` comment; upgrade: `optimize()` at the end of an index run.
- **`lancedb.connect` creates folders.** Only `open_index`'s check keeps search read-only; `test_open_index_missing_creates_nothing`, `test_no_index_exits_2` and `test_search_is_read_only` guard it. `LanceStore.__init__` itself still creates `store/` (E7 relies on that).
- **The UI process and concurrent indexing.** Readers see a consistent Lance version; `read_consistency_interval=timedelta(0)` makes each search check for a newer one (one small metadata read). If that measurably slows UI search, use a 1 s interval (T1).
- **Static scenes crowd the top k** (card 5); short utterances embed poorly. Watch in the demo.
- **Lance file format.** Pinned by `uv.lock`; an upgrade is a dependency card that must open an old store.
- **`filterwarnings = error`.** A warning from lancedb, pyarrow, onnxruntime or tokenizers fails the suite. Fix the call; never add a filter without a card.

## T1 calls (list them in the PR)
1. Embedder in `vision/embed.py`, per M1.
2. `lance-fake` contract param, folder from `tempfile.mkdtemp()`.
3. Ties at the cut settled with a second `distance_range` query; sort key `(-score, asset_id, start_s, modality, end_s, text)`.
4. `score` clamped to [-1, 1].
5. `BATCH_SIZE = 32`; CPU provider only; `cfg` unused by `OnnxEmbedder`.
6. Table created on the first upsert; a reader re-checks for it on search. Open errors wrapped in `StoreError`.
7. `--asset` must match ADR 0012's shape; blank query exits 2; `--k` has `min=1`.
8. Human output escapes with `str.isprintable`; times as `H:MM:SS.cc`.
9. `open_index` / `search_index` in `store/lance.py`, cached per out_dir; the CLI uses `open_index` uncached.
10. `read_consistency_interval=timedelta(0)` (or `checkout_latest()` per search).
11. Two registration lines in `cli/__init__.py`, like E7.

## Decision cards
All decided (table at the top). The r2 card texts are summarised here so the reasoning stays on record.

### Card 1 (T3, on-disk format): the table schema, versioned without migration. Decided A.
Options were A (metadata in the table's schema, refuse mismatches), B (sidecar JSON; can drift after a crash), C (no check; a pin change silently mixes vector spaces). Hardest to reverse: the column set and the meaning of format "1". Would change it: the owner wants v0.2 to upgrade v0.1 indexes in place; then freeze format "1" now and write a migration with the first bump (A allows that).

### Card 2 (T3, CLI flag): `--out DIR` on `search`. Decided A.
Options were A (add `--out`, same meaning as `index --out`), B (config file only), C (a positional `INDEX`, clashes with the query). A shipped flag is permanent; it is the one users need for the two-command flow.

### Card 3 (T3, output shape): human output. Decided A.
Options were A (quoted, escaped, delimited, plain echo), B (rich table; markup injection), C (TSV; a second machine format). A is declared not machine-stable, so it stays cheap to change; scripts use `--json`, the UI uses `search_index`.

### Card 4 (T2): flat search, no ANN index in v0.1. Decided A.
Revisit at about 200 media hours or over 1 s at 500k rows in CI.

### Card 5 (T2, ranking): no near-duplicate collapsing. Decided A.
Revisit if the demo or X1 shows the right moment pushed out of the top 5 by duplicates; then collapse in `LanceStore.search` by an M1 card.

### Card 6 (T2, cross-spec): `StoreError`, exit 2 in both CLIs. Decided A.
Already reflected in approved E7.

### Card 7 (T2): one writer, no lock. Decided A.
If a guard is ever wanted, it belongs in E7 (lock `out_dir` for the run).
