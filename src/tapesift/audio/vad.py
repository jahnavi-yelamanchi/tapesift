"""SileroVAD: Silero v6 ONNX, bundled in faster-whisper (owner Q5: laptop tests, no fetch)."""

from __future__ import annotations

from typing import Any, Final, cast

from tapesift.config import Config, ModelLoadError
from tapesift.media.types import AudioChunk

SILERO_OPTIONS: Final[dict[str, Any]] = {
    "threshold": 0.5,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200,
}
_RATE: Final = 16_000


class SileroVAD:
    def __init__(self, cfg: Config) -> None:
        """Imports faster_whisper.vad here (R6) and loads the model once (get_vad_model()).
        Any exception becomes ModelLoadError(f"cannot load Silero VAD: {type(e).__name__}: {e}").
        cfg is unused in v0.1."""
        try:
            from faster_whisper import vad  # pyright: ignore[reportMissingTypeStubs]

            self._vad: Any = vad
            self._options: Any = vad.VadOptions(**SILERO_OPTIONS)
            vad.get_vad_model()
        except Exception as e:
            raise ModelLoadError(f"cannot load Silero VAD: {type(e).__name__}: {e}") from e

    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]:
        """M1 VAD. get_speech_timestamps(chunk.samples, VadOptions(**SILERO_OPTIONS),
        sampling_rate=16000), each index i mapped to chunk.start_s + i / 16000.
        ValueError if chunk.sample_rate != 16000."""
        if chunk.sample_rate != _RATE:
            raise ValueError(f"SileroVAD needs 16000 Hz audio, got {chunk.sample_rate}")
        found = cast(
            "list[dict[str, int]]",
            self._vad.get_speech_timestamps(chunk.samples, self._options, sampling_rate=_RATE),
        )
        return [
            (chunk.start_s + d["start"] / _RATE, chunk.start_s + d["end"] / _RATE) for d in found
        ]
