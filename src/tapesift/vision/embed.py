"""E6: M1's text Embedder on the pinned bge-small-en-v1.5, ONNX on CPU (onnxruntime + tokenizers,
no torch). Loads only EMBEDDER.files through hub.fetch_pin (R4). Imported lazily (R6)."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any, Final, Literal

import numpy as np
from numpy.typing import NDArray

import tapesift.hub
from tapesift.config import EMBEDDER, Config, ModelLoadError

QUERY_PREFIX: Final = "Represent this sentence for searching relevant passages: "  # bge model card
MAX_TOKENS: Final = 512  # prefix and [CLS]/[SEP] included (card 8: truncate)
BATCH_SIZE: Final = 32
DIM: Final = 384
MODEL_INPUTS: Final = ("input_ids", "attention_mask", "token_type_ids")


class OnnxEmbedder:
    """bge-small-en-v1.5: CLS pooling, then L2 normalization. kind="query" prepends QUERY_PREFIX."""

    def __init__(self, cfg: Config) -> None:  # cfg unused in v0.1
        d = tapesift.hub.fetch_pin(EMBEDDER)
        where = f"cannot load {EMBEDDER.repo}@{EMBEDDER.revision[:12]}"
        try:
            tokenizers: Any = importlib.import_module("tokenizers")
            onnxruntime: Any = importlib.import_module("onnxruntime")
            tok: Any = tokenizers.Tokenizer.from_file(str(d / "tokenizer.json"))
            tok.enable_truncation(MAX_TOKENS)
            tok.enable_padding(pad_id=0, pad_token="[PAD]")  # noqa: S106
            session: Any = onnxruntime.InferenceSession(
                str(d / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"]
            )
            inputs: list[str] = [i.name for i in session.get_inputs()]
            width = session.get_outputs()[0].shape[-1]
        except Exception as e:
            raise ModelLoadError(f"{where}: {type(e).__name__}: {e}") from e
        if "input_ids" not in inputs or not set(inputs) <= set(MODEL_INPUTS):
            raise ModelLoadError(f"{where}: unexpected model inputs {inputs}")
        if width != DIM:
            raise ModelLoadError(f"{where}: output width {width}, expected {DIM}")
        self._tok = tok
        self._session = session
        self._inputs = inputs

    @property
    def id(self) -> str:
        return EMBEDDER.id

    @property
    def dim(self) -> int:
        return DIM

    def embed_text(
        self, texts: Sequence[str], *, kind: Literal["query", "passage"]
    ) -> NDArray[np.float32]:
        if kind not in ("query", "passage"):
            raise ValueError(f"unknown kind {kind!r}")
        if not texts:
            return np.empty((0, DIM), np.float32)
        prefix = QUERY_PREFIX if kind == "query" else ""
        out: list[NDArray[np.float32]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            enc: list[Any] = self._tok.encode_batch([prefix + t for t in texts[i : i + BATCH_SIZE]])
            arrays = {
                "input_ids": [e.ids for e in enc],
                "attention_mask": [e.attention_mask for e in enc],
                "token_type_ids": [e.type_ids for e in enc],
            }
            feed = {n: np.asarray(arrays[n], dtype=np.int64) for n in self._inputs}
            hidden: Any = self._session.run(None, feed)[0]
            cls = np.asarray(hidden[:, 0, :], dtype=np.float32)
            norm = np.maximum(np.linalg.norm(cls, axis=1, keepdims=True), 1e-12)
            out.append((cls / norm).astype(np.float32))
        return np.ascontiguousarray(np.concatenate(out), dtype=np.float32)
