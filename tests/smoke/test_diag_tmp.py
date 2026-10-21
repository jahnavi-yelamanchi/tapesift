"""TEMPORARY diagnostic (to be deleted): Whisper's own non-speech signals on the contract inputs."""

import logging

import numpy as np
import pytest

from tapesift.audio.faster_whisper import FasterWhisperASR
from tapesift.config import Config

pytestmark = pytest.mark.model
log = logging.getLogger(__name__)
SR = 16_000
TONE = (0.1 * np.sin(2 * np.pi * 440 * np.arange(2 * SR) / SR)).astype(np.float32)
_B = np.concatenate(
    [0.3 * np.sin(2 * np.pi * 440 * np.arange(int(0.3 * SR)) / SR), np.zeros(int(0.2 * SR))]
)
BURSTS = np.tile(_B, 4).astype(np.float32)
ZEROS = np.zeros(2 * SR, dtype=np.float32)


@pytest.mark.parametrize("name", ["tone", "bursts", "zeros"])
def test_diag(name: str) -> None:
    asr = FasterWhisperASR(Config())
    x = {"tone": TONE, "bursts": BURSTS, "zeros": ZEROS}[name]
    for label, kw in (("default", {}), ("nothresh", {"no_speech_threshold": None})):
        asr._ct2.set_random_seed(0)  # pyright: ignore[reportPrivateUsage]
        segs, info = asr._model.transcribe(  # pyright: ignore[reportPrivateUsage]
            x, language=None, word_timestamps=True, vad_filter=False, **kw
        )
        got = [
            (round(s.no_speech_prob, 3), round(s.avg_logprob, 4), round(s.compression_ratio, 2))
            for s in segs
        ]
        log.info(
            "DIAG %s %s lang_prob=%.2f segs(no_speech, avg_logprob, cr)=%s",
            name,
            label,
            info.language_probability,
            got,
        )
