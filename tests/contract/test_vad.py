"""Contract for tapesift.audio.types.VAD (docs/specs/25-m1-interfaces.md, R1). Real backends join
the `backend` fixture's params later and change nothing else."""

from collections.abc import Callable
from itertools import pairwise

import numpy as np
import pytest

# Each block below is its own isort section: the new interface modules do not exist yet, and ruff
# groups a missing module as third-party until they do. This order is valid before and after.
# isort: split
from tapesift.media.types import AudioChunk

# isort: split
from tapesift.audio.types import VAD

# isort: split
from tests.fakes import FakeVAD

SR = 16_000
_TONE_440 = np.sin(2 * np.pi * 440 * np.arange(int(0.3 * SR)) / SR)
_BURST = np.concatenate([0.3 * _TONE_440, np.zeros(int(0.2 * SR))])
BURSTS = np.tile(_BURST, 4).astype(np.float32)  # 2 s: four 0.3 s tone bursts, 0.2 s gaps
ZEROS = np.zeros(2 * SR, dtype=np.float32)


FAKE: Callable[[], VAD] = FakeVAD  # pyright checks that the fake satisfies the Protocol


@pytest.fixture(params=[pytest.param(FAKE, id="fake")])
def backend(request: pytest.FixtureRequest) -> VAD:
    factory: Callable[[], VAD] = request.param
    return factory()


def test_spans_inside_chunk_sorted(backend: VAD) -> None:
    spans = backend.speech_spans(AudioChunk(600.0, BURSTS, SR))
    if isinstance(backend, FakeVAD):
        assert spans
    assert all(600.0 <= s <= e <= 602.0 for s, e in spans)
    assert all(prev_end <= start for (_, prev_end), (start, _) in pairwise(spans))


def test_silence_has_no_spans(backend: VAD) -> None:
    assert backend.speech_spans(AudioChunk(0.0, ZEROS, SR)) == []
