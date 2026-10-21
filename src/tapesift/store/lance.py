"""E6: M1's Store on embedded LanceDB in out_dir / "store" (spec D5), plus the search API the CLI
and the web UI share. One row per utterance (SPEECH) and per caption (VISUAL); exact (flat) cosine
search, no ANN index (card 4). Schema metadata records the store format and the embedder id; any
other value is refused, never migrated (card 1). One writer at a time (card 7)."""

from __future__ import annotations

import functools
import importlib
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import numpy as np

from tapesift.config import Config
from tapesift.schema.records import AssetRecord, Hit, Modality
from tapesift.vision.types import Embedder

STORE_DIR: Final = "store"
TABLE: Final = "passages"
STORE_FORMAT: Final = "1"  # bump on any change to the columns, their meaning or the passage text
FORMAT_KEY: Final = "tapesift.store_format"
EMBEDDER_KEY: Final = "tapesift.embedder"
_COLUMNS: Final = ("asset_id", "path", "modality", "start_s", "end_s", "text", "media_text")


class StoreError(RuntimeError):
    """The index under out_dir can't be used: missing, not a tapesift store, another store
    format, another embedder, or it can't be opened. CLIs exit 2 (card 6)."""


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


class LanceStore:
    def __init__(self, cfg: Config, embedder: Embedder) -> None:
        self._embedder = embedder
        self._dir = cfg.out_dir / STORE_DIR
        self._lancedb: Any = importlib.import_module("lancedb")
        self._pa: Any = importlib.import_module("pyarrow")
        try:
            self._db: Any = self._lancedb.connect(self._dir, read_consistency_interval=timedelta(0))
            self._table: Any = None
            self._open_table()
        except StoreError:
            raise
        except Exception as e:
            raise StoreError(f"{self._dir}: cannot open the store: {type(e).__name__}: {e}") from e

    def _open_table(self) -> None:
        if TABLE not in self._db.list_tables().tables:
            self._table = None
            return
        table = self._db.open_table(TABLE)
        meta: dict[bytes, bytes] = table.schema.metadata or {}

        def get(key: str) -> str | None:
            v = meta.get(key.encode())
            return None if v is None else v.decode("utf-8", "replace")

        fmt, emb = get(FORMAT_KEY), get(EMBEDDER_KEY) or ""
        if fmt is None:
            raise StoreError(
                f"{self._dir}: not a tapesift store (no {FORMAT_KEY} metadata); "
                "index into a new --out"
            )
        if fmt != STORE_FORMAT:
            raise StoreError(
                f"{self._dir}: unsupported store format {fmt!r} "
                f"(this tapesift reads {STORE_FORMAT!r}); index into a new --out"
            )
        if emb != self._embedder.id:
            raise StoreError(
                f"{self._dir}: indexed with {emb}, but this tapesift embeds with "
                f"{self._embedder.id}; index into a new --out"
            )
        self._table = table

    def _schema(self) -> Any:
        pa = self._pa
        return pa.schema(
            [
                pa.field("asset_id", pa.string(), nullable=False),
                pa.field("path", pa.string(), nullable=False),
                pa.field("modality", pa.string(), nullable=False),
                pa.field("start_s", pa.float64(), nullable=False),
                pa.field("end_s", pa.float64(), nullable=False),
                pa.field("text", pa.string(), nullable=False),
                pa.field("media_text", pa.list_(pa.string()), nullable=False),
                pa.field("vector", pa.list_(pa.float32(), self._embedder.dim), nullable=False),
            ],
            metadata={FORMAT_KEY: STORE_FORMAT, EMBEDDER_KEY: self._embedder.id},
        )

    def upsert(self, record: AssetRecord) -> None:
        aid, path = record.asset.id, str(record.asset.path)
        rows: list[tuple[Modality, float, float, str, list[str], str]] = []
        for u in record.utterances:
            rows.append((Modality.SPEECH, u.start_s, u.end_s, u.text, [], u.text))
        for c in record.captions:
            text = " ".join((c.text, *c.media_text))
            rows.append((Modality.VISUAL, c.t_s, c.t_s, c.text, list(c.media_text), text))
        vectors = None
        if rows:
            vectors = self._embedder.embed_text([r[5] for r in rows], kind="passage")
            if vectors.shape != (len(rows), self._embedder.dim):
                raise ValueError(
                    f"embedder returned shape {vectors.shape}, expected "
                    f"{(len(rows), self._embedder.dim)}"
                )
        if self._table is None:
            self._open_table()
        if self._table is None:
            self._table = self._db.create_table(TABLE, schema=self._schema())
        # ponytail: delete then add is two Lance commits; a crash between leaves the asset with no
        # rows, so the next run re-indexes it. Upgrade: merge_insert. Versions pile up per upsert;
        # upgrade: table.optimize() at the end of an index run.
        self.delete(aid)
        if vectors is None:
            return
        pa = self._pa
        schema = self._schema()
        data = pa.table(
            {
                "asset_id": [aid] * len(rows),
                "path": [path] * len(rows),
                "modality": [r[0].value for r in rows],
                "start_s": [r[1] for r in rows],
                "end_s": [r[2] for r in rows],
                "text": [r[3] for r in rows],
                "media_text": [r[4] for r in rows],
                "vector": pa.FixedSizeListArray.from_arrays(
                    pa.array(np.ascontiguousarray(vectors).ravel(), pa.float32()),
                    self._embedder.dim,
                ),
            },
            schema=schema,
        )
        self._table.add(data)

    def delete(self, asset_id: str) -> None:
        if self._table is None:
            return
        self._table.delete(f"asset_id = {_q(asset_id)}")

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        modality: Modality | None = None,
        asset_id: str | None = None,
    ) -> list[Hit]:
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        if self._table is None:
            self._open_table()
        if self._table is None:
            return []
        filters: list[str] = []
        if modality is not None:
            filters.append(f"modality = {_q(modality.value)}")
        if asset_id is not None:
            filters.append(f"asset_id = {_q(asset_id)}")
        where = " AND ".join(filters) or None
        n: int = self._table.count_rows(where)
        if n == 0:
            return []
        v = self._embedder.embed_text([query], kind="query")[0]
        # ponytail: flat (exact) search, no ANN index; ceiling about 1M rows. Upgrade: an IVF
        # index behind a row-count threshold.
        base: Any = (
            self._table.search(v, vector_column_name="vector")
            .distance_type("cosine")
            .select([*_COLUMNS, "_distance"])  # naming _distance silences a lance deprecation log
        )
        if where is not None:
            base = base.where(where, prefilter=True)
        rows: list[dict[str, Any]] = base.limit(min(k, n)).to_list()
        if len(rows) == k < n:  # ties at the cut: take everything not worse than the k-th
            d_k = max(r["_distance"] for r in rows)
            upper = float(np.nextafter(np.float32(d_k), np.float32(2.0)))
            rows = base.distance_range(None, upper).limit(n).to_list()
        hits = [
            Hit(
                r["asset_id"],
                r["path"],
                float(r["start_s"]),
                float(r["end_s"]),
                Modality(r["modality"]),
                r["text"],
                tuple(r["media_text"]),
                float(min(1.0, max(-1.0, 1.0 - r["_distance"]))),
            )
            for r in rows
        ]
        hits.sort(
            key=lambda h: (-h.score, h.asset_id, h.start_s, h.modality.value, h.end_s, h.text)
        )
        return hits[:k]


def load_embedder() -> Embedder:
    """OnnxEmbedder(Config()), imported here (R6). Tests patch this module attribute."""
    from tapesift.vision.embed import OnnxEmbedder

    return OnnxEmbedder(Config())


def open_index(out_dir: Path) -> LanceStore:
    """An existing index, opened for searching. In order:
    1. (out_dir / STORE_DIR) is not a folder: StoreError(f'no index at {out_dir}: run "tapesift
       index" first, or pass --out'). Nothing is created and no model loads.
    2. embedder = load_embedder()  (ModelLoadError propagates)
    3. LanceStore(Config(out_dir=out_dir), embedder)  (StoreError on another format or embedder)"""
    if not (out_dir / STORE_DIR).is_dir():
        raise StoreError(f'no index at {out_dir}: run "tapesift index" first, or pass --out')
    return LanceStore(Config(out_dir=out_dir), load_embedder())


# ponytail: unbounded per-process cache, one entry per out_dir; two threads racing the first call
# may both load the model (harmless).
_open_cached = functools.cache(open_index)


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
    idx = _open_cached(out_dir.resolve())
    return idx.search(query, k, modality=modality, asset_id=asset_id)
