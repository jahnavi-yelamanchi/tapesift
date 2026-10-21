"""LanceStore, open_index and search_index (docs/specs/29-search.md, E6 unit tests).
FakeEmbedder only; the Store contract itself runs in tests/contract/test_store.py."""

import dataclasses
import json
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Literal

import lancedb
import numpy as np
import pyarrow as pa
import pytest
from numpy.typing import NDArray
from tests.fakes import FakeEmbedder

import tapesift
from tapesift.config import Config
from tapesift.media.types import AssetInfo
from tapesift.schema.records import AssetRecord, Caption, Hit, Modality, Provenance, Utterance
from tapesift.store import lance
from tapesift.store.lance import LanceStore, StoreError, open_index, search_index

Z = "0" * 40
A_ID = "tsid1:" + "a" * 64
B_ID = "tsid1:" + "b" * 64
QUERY = "quarterly pricing review"


def prov(asr: bool, vlm: bool) -> Provenance:
    return Provenance(
        tapesift.__version__,
        "fake:asr@" + Z if asr else None,
        "fake:vlm@" + Z if vlm else None,
        "caption_v1" if vlm else None,
    )


def record(
    asset_id: str,
    path: str,
    duration: float,
    utterances: tuple[Utterance, ...] = (),
    captions: tuple[Caption, ...] = (),
) -> AssetRecord:
    asset = AssetInfo(asset_id, Path(path), duration, None, (), ())
    return AssetRecord(asset, utterances, captions, (), prov(bool(utterances), bool(captions)))


def utt(start_s: float, end_s: float, text: str) -> Utterance:
    return Utterance(start_s, end_s, text, "en", 1.0, ())


A = record(
    A_ID,
    "/media/talk.mp4",
    10.0,
    utterances=(
        utt(1.5, 4.25, "The quarterly pricing review starts at nine."),
        utt(5.0, 8.0, "Revenue grew twelve percent while costs stayed flat."),
    ),
)
B = record(
    B_ID,
    "/media/slides.mp4",
    100.0,
    captions=(Caption(62.0, "a slide", 1.0, ("BUY NOW",)), Caption(63.0, "a chart", None, ())),
)


class OtherEmbedder(FakeEmbedder):
    id = "fake:other@" + Z


class SpyEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.log: list[tuple[list[str], str]] = []

    def embed_text(
        self, texts: Sequence[str], *, kind: Literal["query", "passage"]
    ) -> NDArray[np.float32]:
        self.log.append((list(texts), kind))
        return super().embed_text(texts, kind=kind)


class FlakyEmbedder(FakeEmbedder):
    fail = False

    def embed_text(
        self, texts: Sequence[str], *, kind: Literal["query", "passage"]
    ) -> NDArray[np.float32]:
        if self.fail:
            raise RuntimeError("embed")
        return super().embed_text(texts, kind=kind)


def make(out: Path, embedder: FakeEmbedder | None = None) -> LanceStore:
    return LanceStore(Config(out_dir=out), embedder or FakeEmbedder())


def seeded(out: Path, *records: AssetRecord) -> LanceStore:
    store = make(out)
    for r in records:
        store.upsert(r)
    return store


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    lance._open_cached.cache_clear()
    yield
    lance._open_cached.cache_clear()


def _table(out: Path) -> lancedb.table.Table:
    return lancedb.connect(out / "store").open_table("passages")


def test_table_schema_exact(tmp_path: Path) -> None:
    seeded(tmp_path, A)
    schema = _table(tmp_path).schema
    assert schema.names == [
        "asset_id",
        "path",
        "modality",
        "start_s",
        "end_s",
        "text",
        "media_text",
        "vector",
    ]
    assert [f.nullable for f in schema] == [False] * 8
    assert [f.type for f in schema] == [
        pa.string(),
        pa.string(),
        pa.string(),
        pa.float64(),
        pa.float64(),
        pa.string(),
        pa.list_(pa.string()),
        pa.list_(pa.float32(), 256),
    ]
    assert schema.metadata == {
        b"tapesift.store_format": b"1",
        b"tapesift.embedder": b"fake:embedder@" + Z.encode(),
    }


def test_passage_texts_and_kind(tmp_path: Path) -> None:
    spy = SpyEmbedder()
    store = make(tmp_path, spy)
    store.upsert(B)
    assert spy.log == [(["a slide BUY NOW", "a chart"], "passage")]
    store.search("a chart")
    assert spy.log[1:] == [(["a chart"], "query")]


def test_embed_failure_keeps_old_rows(tmp_path: Path) -> None:
    flaky = FlakyEmbedder()
    store = make(tmp_path, flaky)
    store.upsert(A)
    flaky.fail = True
    a2 = record(A_ID, "/media/talk.mp4", 10.0, utterances=(utt(0.0, 1.0, "charlie delta"),))
    with pytest.raises(RuntimeError, match="embed"):
        store.upsert(a2)
    flaky.fail = False
    hits = store.search(QUERY, k=100)
    assert [h.text for h in hits] == [
        "The quarterly pricing review starts at nine.",
        "Revenue grew twelve percent while costs stayed flat.",
    ]


def test_reopen_sees_rows(tmp_path: Path) -> None:
    seeded(tmp_path, A, B)
    hits = make(tmp_path).search(QUERY)
    assert hits[0].asset_id == A_ID
    assert len(hits) == 4


def test_search_is_read_only(tmp_path: Path) -> None:
    seeded(tmp_path, A, B)

    def snapshot() -> dict[str, tuple[int, int]]:
        files = [p for p in tmp_path.rglob("*") if p.is_file()]
        return {
            p.relative_to(tmp_path).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in files
        }

    before = snapshot()
    assert before
    store = make(tmp_path)
    store.search(QUERY)
    store.search(QUERY, modality=Modality.VISUAL)
    store.search(QUERY, asset_id=A_ID)
    assert snapshot() == before


def test_embedder_mismatch_refused(tmp_path: Path) -> None:
    seeded(tmp_path, A)
    with pytest.raises(StoreError) as err:
        make(tmp_path, OtherEmbedder())
    assert str(err.value) == (
        f"{tmp_path / 'store'}: indexed with fake:embedder@{Z}, but this tapesift embeds with "
        f"fake:other@{Z}; index into a new --out"
    )


def test_other_format_refused(tmp_path: Path) -> None:
    def table_with(out: Path, metadata: dict[str, str] | None) -> None:
        schema = pa.schema([pa.field("asset_id", pa.string(), nullable=False)], metadata=metadata)
        lancedb.connect(out / "store").create_table("passages", schema=schema)

    v2, bare = tmp_path / "v2", tmp_path / "bare"
    table_with(v2, {"tapesift.store_format": "2"})
    table_with(bare, None)
    with pytest.raises(StoreError) as err:
        make(v2)
    assert str(err.value) == (
        f"{v2 / 'store'}: unsupported store format '2' (this tapesift reads '1'); "
        "index into a new --out"
    )
    with pytest.raises(StoreError) as err:
        make(bare)
    assert str(err.value).endswith("(no tapesift.store_format metadata); index into a new --out")


def test_ties_cut_by_asset_then_start(tmp_path: Path) -> None:
    f_id, zero_id = "tsid1:" + "f" * 64, "tsid1:" + "0" * 64
    captions = (Caption(0.0, "same text", 1.0, ()), Caption(1.0, "same text", 1.0, ()))
    store = seeded(
        tmp_path,
        record(f_id, "/media/f.mp4", 10.0, captions=captions),
        record(zero_id, "/media/0.mp4", 10.0, captions=captions),
    )

    def keys(k: int) -> list[tuple[str, float]]:
        return [(h.asset_id, h.start_s) for h in store.search("same text", k=k)]

    assert keys(1) == [(zero_id, 0.0)]
    assert keys(3) == [(zero_id, 0.0), (zero_id, 1.0), (f_id, 0.0)]


def test_quotes_in_ids_are_escaped(tmp_path: Path) -> None:
    quoted = record("x'y", "/media/q.mp4", 10.0, utterances=(utt(0.0, 1.0, "alpha beta"),))
    store = seeded(tmp_path, quoted, A)
    found = store.search("alpha beta", k=100, asset_id="x'y")
    assert [(h.asset_id, h.text) for h in found] == [("x'y", "alpha beta")]
    assert store.search("alpha beta", k=100, asset_id="x' OR '1'='1") == []
    store.delete("x'y")
    left = store.search("alpha beta", k=100)
    assert {h.asset_id for h in left} == {A_ID}
    assert len(left) == 2


def test_hit_fields_and_clamped_score(tmp_path: Path) -> None:
    store = seeded(tmp_path, B)
    hits = store.search("a chart", k=100)
    assert hits[0].text == "a chart"
    assert hits[0].score == 1.0
    assert len(hits) == 2
    for hit in hits:
        assert type(hit.score) is float
        assert isinstance(hit.media_text, tuple)
        assert all(type(m) is str for m in hit.media_text)
        assert isinstance(hit.modality, Modality)
        assert hit.trust == "untrusted_media"
        json.dumps(dataclasses.asdict(hit))
    assert hits[1].media_text == ("BUY NOW",)


def test_open_index_missing_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded: list[int] = []

    def counting() -> FakeEmbedder:
        loaded.append(1)
        return FakeEmbedder()

    monkeypatch.setattr(lance, "load_embedder", counting)
    o = tmp_path / "o"
    with pytest.raises(StoreError) as err:
        open_index(o)
    assert str(err.value) == f'no index at {o}: run "tapesift index" first, or pass --out'
    assert not o.exists()
    assert loaded == []


def test_search_index_loads_model_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seeded(tmp_path, A, B)
    loaded: list[int] = []

    def counting() -> FakeEmbedder:
        loaded.append(1)
        return FakeEmbedder()

    monkeypatch.setattr(lance, "load_embedder", counting)
    first = search_index(QUERY, tmp_path)
    second = search_index(QUERY, tmp_path)
    assert first == second
    assert all(isinstance(h, Hit) for h in first)
    assert first[0].path == "/media/talk.mp4"
    assert (first[0].start_s, first[0].end_s) == (1.5, 4.25)
    assert loaded == [1]


def test_long_lived_index_sees_new_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory: Callable[[], FakeEmbedder] = FakeEmbedder
    monkeypatch.setattr(lance, "load_embedder", factory)
    make(tmp_path)  # creates the store folder, no table yet
    idx = open_index(tmp_path)
    assert idx.search(QUERY) == []
    writer = make(tmp_path)
    writer.upsert(A)
    assert idx.search(QUERY)[0].asset_id == A_ID
    writer.upsert(B)
    hits = idx.search("a chart", modality=Modality.VISUAL)
    assert hits[0].asset_id == B_ID
    assert hits[0].text == "a chart"
