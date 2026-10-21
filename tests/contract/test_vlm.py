"""Contract for tapesift.vision.types.VLM (docs/specs/25-m1-interfaces.md, R1, R3)."""

from collections.abc import Callable

import numpy as np
import pytest

# Each block below is its own isort section: the new interface modules do not exist yet, and ruff
# groups a missing module as third-party until they do. This order is valid before and after.
# isort: split
from tapesift.config import Config
from tapesift.media.types import Frame

# isort: split
from tapesift.schema.records import BACKEND_ID_RE
from tapesift.vision.types import VLM

# isort: split
from tapesift.vision.transformers_vlm import TransformersVLM

# isort: split
from tests.fakes import FakeVLM


def _frames(*times: float) -> list[Frame]:
    return [Frame(t, np.full((48, 64, 3), 128, dtype=np.uint8)) for t in times]


FAKE: Callable[[], VLM] = FakeVLM  # pyright checks that the fake satisfies the Protocol


@pytest.fixture(
    params=[
        pytest.param(FAKE, id="fake"),
        pytest.param(lambda: TransformersVLM(Config()), id="transformers", marks=pytest.mark.model),
    ]
)
def backend(request: pytest.FixtureRequest) -> VLM:
    factory: Callable[[], VLM] = request.param
    return factory()


def test_one_caption_per_frame_in_order(backend: VLM) -> None:
    captions = backend.caption(_frames(0.0, 1.0, 2.5), "caption_v1")
    assert [c.t_s for c in captions] == [0.0, 1.0, 2.5]


def test_empty_input_returns_empty(backend: VLM) -> None:
    assert backend.caption([], "caption_v1") == []


def test_unknown_prompt_rejected(backend: VLM) -> None:
    with pytest.raises(ValueError):
        backend.caption(_frames(0.0), "nope")


def test_caption_fields_typed(backend: VLM) -> None:
    captions = backend.caption(_frames(0.0, 1.0), "caption_v1")
    assert captions
    for c in captions:
        assert isinstance(c.media_text, tuple)
        assert all(isinstance(w, str) for w in c.media_text)
        assert c.conf is None or 0.0 <= c.conf <= 1.0


def test_id_matches_backend_id_format(backend: VLM) -> None:
    assert BACKEND_ID_RE.fullmatch(backend.id)
