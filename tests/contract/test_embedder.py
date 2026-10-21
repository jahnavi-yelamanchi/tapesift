"""Contract for tapesift.vision.types.Embedder (docs/specs/25-m1-interfaces.md, card 8, R3)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pytest

# Each block below is its own isort section: the new interface modules do not exist yet, and ruff
# groups a missing module as third-party until they do. This order is valid before and after.
# isort: split
from tapesift.config import Config
from tapesift.schema.records import BACKEND_ID_RE
from tapesift.vision.embed import OnnxEmbedder
from tapesift.vision.types import Embedder

# isort: split
from tests.fakes import FakeEmbedder

MANIFEST = Path(__file__).parents[1] / "fixtures" / "manifest.json"


FAKE: Callable[[], Embedder] = FakeEmbedder  # pyright checks that the fake satisfies the Protocol


@pytest.fixture(
    params=[
        pytest.param(FAKE, id="fake"),
        pytest.param(lambda: OnnxEmbedder(Config()), id="onnx", marks=pytest.mark.model),
    ]
)
def backend(request: pytest.FixtureRequest) -> Embedder:
    factory: Callable[[], Embedder] = request.param
    return factory()


def test_shape_and_dtype(backend: Embedder) -> None:
    out = backend.embed_text(["a", "b c", "d e f"], kind="passage")
    assert out.shape == (3, backend.dim)
    assert out.dtype == np.float32


@pytest.mark.parametrize("kind", ["query", "passage"])
def test_rows_are_unit_length(backend: Embedder, kind: Literal["query", "passage"]) -> None:
    out = backend.embed_text(["", "a", "quarterly pricing review"], kind=kind)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-5, rtol=0)


def test_deterministic(backend: Embedder) -> None:
    texts = ["quarterly pricing review", "", "a red square"]
    first = backend.embed_text(texts, kind="passage")
    assert np.array_equal(first, backend.embed_text(texts, kind="passage"))


def test_empty_input_shape(backend: Embedder) -> None:
    assert backend.embed_text([], kind="passage").shape == (0, backend.dim)


def test_related_text_scores_higher(backend: Embedder) -> None:
    entries: list[Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))["fixtures"]
    transcript = next(e for e in entries if e["name"] == "speech.mp4")["transcript"]
    q = backend.embed_text(["quarterly pricing review"], kind="query")[0]
    a = backend.embed_text([transcript], kind="passage")[0]
    b = backend.embed_text(["a red square on a blue background"], kind="passage")[0]
    assert q @ a > q @ b


def test_long_text_is_truncated_not_rejected(backend: Embedder) -> None:
    out = backend.embed_text([" ".join(["word"] * 5000)], kind="passage")
    assert out.shape == (1, backend.dim)
    assert abs(float(np.linalg.norm(out[0])) - 1.0) < 1e-5


def test_id_matches_backend_id_format(backend: Embedder) -> None:
    assert BACKEND_ID_RE.fullmatch(backend.id)
