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
