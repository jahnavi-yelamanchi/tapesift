"""Contract for tapesift.audio.types.ASR (docs/specs/25-m1-interfaces.md, R1, R3)."""

from collections.abc import Callable

import numpy as np
import pytest

# Each block below is its own isort section: the new interface modules do not exist yet, and ruff
# groups a missing module as third-party until they do. This order is valid before and after.
# isort: split
from tapesift.media.types import AudioChunk

# isort: split
from tapesift.audio.types import ASR
from tapesift.schema.records import BACKEND_ID_RE

# isort: split
from tests.fakes import FakeASR

SR = 16_000
_TONE_440 = np.sin(2 * np.pi * 440 * np.arange(int(0.3 * SR)) / SR)
_BURST = np.concatenate([0.3 * _TONE_440, np.zeros(int(0.2 * SR))])
BURSTS = np.tile(_BURST, 4).astype(np.float32)  # 2 s: four 0.3 s tone bursts, 0.2 s gaps
TONE = (0.1 * np.sin(2 * np.pi * 440 * np.arange(2 * SR) / SR)).astype(np.float32)
ZEROS = np.zeros(2 * SR, dtype=np.float32)


FAKE: Callable[[], ASR] = FakeASR  # pyright checks that the fake satisfies the Protocol


@pytest.fixture(params=[pytest.param(FAKE, id="fake")])
def backend(request: pytest.FixtureRequest) -> ASR:
    factory: Callable[[], ASR] = request.param
    return factory()


def test_one_result_list_per_chunk(backend: ASR) -> None:
    chunks = [AudioChunk(0.0, a, SR) for a in (BURSTS, ZEROS, TONE)]
    assert len(backend.transcribe(chunks)) == 3


def test_empty_input_returns_empty(backend: ASR) -> None:
    assert backend.transcribe([]) == []


def test_times_on_container_clock(backend: ASR) -> None:
    (utterances,) = backend.transcribe([AudioChunk(600.0, BURSTS, SR)])
    if isinstance(backend, FakeASR):
        assert utterances
    assert all(600.0 <= u.start_s <= 602.0 and 600.0 <= u.end_s <= 603.0 for u in utterances)


def test_id_matches_backend_id_format(backend: ASR) -> None:
    assert BACKEND_ID_RE.fullmatch(backend.id)
