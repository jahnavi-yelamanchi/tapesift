"""OnnxEmbedder (docs/specs/29-search.md, "tests/unit/test_embed_onnx.py"): a stub ONNX session and
a test-built tokenizer.json stand in for the pinned bge-small weights (ADR 0008). No network."""

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import numpy as np
import onnxruntime
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray
from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors

import tapesift.hub
from tapesift.config import EMBEDDER, Config, ModelLoadError
from tapesift.vision.embed import (
    BATCH_SIZE,
    DIM,
    MAX_TOKENS,
    MODEL_INPUTS,
    QUERY_PREFIX,
    OnnxEmbedder,
)

WORDS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
PAD, UNK, CLS, SEP = 0, 1, 2, 3
UNKNOWN_PIECE = "[UNK]"
PREFIX_WORDS = ["represent", "this", "sentence", "for", "searching", "relevant", "passages", ":"]


def _build_tokenizer() -> Tokenizer:
    vocab = {"[PAD]": PAD, UNKNOWN_PIECE: UNK, "[CLS]": CLS, "[SEP]": SEP}
    for w in (*PREFIX_WORDS, *WORDS):
        vocab.setdefault(w, len(vocab))
    tok = Tokenizer(models.WordLevel(vocab, unk_token=UNKNOWN_PIECE))
    tok.normalizer = normalizers.Lowercase()
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", CLS), ("[SEP]", SEP)]
    )
    return tok


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("bge-snapshot")
    (d / "onnx").mkdir()
    (d / "onnx" / "model.onnx").write_bytes(b"")
    _build_tokenizer().save(str(d / "tokenizer.json"))
    return d


class StubSession:
    """Stands in for onnxruntime.InferenceSession. Row b of the output has a bag-of-ids vector at
    position 0 (the CLS slot) and 1e3 everywhere else, so any pooling but CLS fails."""

    def __init__(
        self,
        *,
        width: int = DIM,
        inputs: Sequence[str] = MODEL_INPUTS,
        error: Exception | None = None,
    ) -> None:
        self.width = width
        self.inputs = tuple(inputs)
        self.error = error
        self.opened: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.feeds: list[dict[str, NDArray[Any]]] = []
        self.cls_rows: list[NDArray[np.float32]] = []

    def open(self, *args: Any, **kwargs: Any) -> "StubSession":
        if self.error is not None:
            raise self.error
        self.opened.append((args, kwargs))
        return self

    def get_inputs(self) -> list[Any]:
        return [SimpleNamespace(name=n) for n in self.inputs]

    def get_outputs(self) -> list[Any]:
        return [SimpleNamespace(name="last_hidden_state", shape=["batch", "seq", self.width])]

    def run(self, output_names: Any, feed: dict[str, NDArray[Any]]) -> list[NDArray[np.float32]]:
        self.feeds.append(feed)
        ids, mask = feed["input_ids"], feed["attention_mask"]
        batch, seq = ids.shape
        hidden = np.full((batch, seq, self.width), 1e3, dtype=np.float32)
        for b in range(batch):
            v = np.zeros(self.width, dtype=np.float32)
            for i, m in zip(ids[b], mask[b], strict=True):
                if m:
                    v[(int(i) * 7 + 1) % self.width] += 1.0
            hidden[b, 0, :] = v
            self.cls_rows.append(v)
        return [hidden]


def _build(mp: pytest.MonkeyPatch, snapshot: Path, stub: StubSession) -> OnnxEmbedder:
    mp.setattr(tapesift.hub, "fetch_pin", lambda pin: snapshot)
    mp.setattr(onnxruntime, "InferenceSession", stub.open)
    return OnnxEmbedder(Config())


def _texts(n: int) -> list[str]:
    """n distinct texts of varying length, so batches need padding."""
    return [" ".join(WORDS[(i + j) % len(WORDS)] for j in range(1 + i % 5)) for i in range(n)]


def _normalized(rows: Sequence[NDArray[np.float32]]) -> NDArray[np.float32]:
    cls = np.stack(rows).astype(np.float32)
    return cls / np.linalg.norm(cls, axis=1, keepdims=True)


def _ids(snapshot: Path, text: str) -> list[int]:
    return Tokenizer.from_file(str(snapshot / "tokenizer.json")).encode(text).ids


@settings(max_examples=25, deadline=None)
@given(
    texts=st.lists(
        st.lists(st.sampled_from(WORDS), max_size=8).map(" ".join), min_size=1, max_size=40
    ),
    kind=st.sampled_from(["query", "passage"]),
)
def test_id_dim_and_cls_pooling(
    snapshot: Path, texts: list[str], kind: Literal["query", "passage"]
) -> None:
    stub = StubSession()
    with pytest.MonkeyPatch.context() as mp:
        emb = _build(mp, snapshot, stub)
    assert emb.id == "onnx:bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    assert emb.id == EMBEDDER.id
    assert emb.dim == 384
    assert stub.opened[0][1]["providers"] == ["CPUExecutionProvider"]
    out = emb.embed_text(texts, kind=kind)
    assert out.dtype == np.float32
    assert out.shape == (len(texts), 384)
    assert out.flags["C_CONTIGUOUS"]
    np.testing.assert_allclose(out, _normalized(stub.cls_rows), atol=1e-6, rtol=0)


def test_query_prefix_only_for_queries(snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubSession()
    emb = _build(monkeypatch, snapshot, stub)
    assert QUERY_PREFIX.startswith("Represent this sentence")
    emb.embed_text(["alpha beta"], kind="query")
    emb.embed_text(["alpha beta"], kind="passage")
    query_row, passage_row = (f["input_ids"][0].tolist() for f in stub.feeds)
    prefix_ids = _ids(snapshot, QUERY_PREFIX)[1:-1]  # drop [CLS] and [SEP]
    text_ids = _ids(snapshot, "alpha beta")[1:-1]
    assert UNK not in prefix_ids  # the test vocabulary covers the prefix, ":" included
    assert query_row[: 1 + len(prefix_ids)] == [CLS, *prefix_ids]
    assert query_row == [CLS, *prefix_ids, *text_ids, SEP]
    assert passage_row == [CLS, *text_ids, SEP]


def test_truncates_to_512_tokens(snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubSession()
    emb = _build(monkeypatch, snapshot, stub)
    out = emb.embed_text([" ".join(["alpha"] * 5000)], kind="passage")
    (feed,) = stub.feeds
    row = feed["input_ids"][0].tolist()
    assert MAX_TOKENS == 512
    assert len(row) == 512
    assert row[0] == CLS
    assert row[-1] == SEP
    assert out.shape == (1, 384)
    assert abs(float(np.linalg.norm(out[0])) - 1.0) < 1e-5


def test_batches_of_32_in_order(snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubSession()
    emb = _build(monkeypatch, snapshot, stub)
    texts = _texts(70)
    out = emb.embed_text(texts, kind="passage")
    assert BATCH_SIZE == 32
    assert [f["input_ids"].shape[0] for f in stub.feeds] == [32, 32, 6]
    assert all(f["input_ids"].dtype == np.int64 for f in stub.feeds)
    assert set(stub.feeds[0]) == set(MODEL_INPUTS)
    assert out.shape == (70, 384)
    for i in (0, 1, 31, 32, 33, 63, 64, 69):
        single = emb.embed_text([texts[i]], kind="passage")[0]
        np.testing.assert_allclose(out[i], single, atol=1e-6, rtol=0)


PREFIX = "cannot load BAAI/bge-small-en-v1.5@5c38ec7c405e: "


@pytest.mark.parametrize(
    ("stub", "tail", "exact"),
    [
        pytest.param(
            StubSession(error=RuntimeError("bad onnx")),
            "RuntimeError: bad onnx",
            True,
            id="session",
        ),
        pytest.param(StubSession(width=256), "output width 256, expected 384", False, id="width"),
    ],
)
def test_load_errors_are_model_load_error(
    snapshot: Path, monkeypatch: pytest.MonkeyPatch, stub: StubSession, tail: str, exact: bool
) -> None:
    with pytest.raises(ModelLoadError) as err:
        _build(monkeypatch, snapshot, stub)
    message = str(err.value)
    assert message.endswith(tail)
    assert message.startswith(PREFIX)
    if exact:
        assert message == PREFIX + tail
