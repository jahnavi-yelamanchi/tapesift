"""The VAD and ASR backend Protocols. E3 implements them (Silero via faster_whisper.vad, and
faster-whisper); tests use tests/fakes.py."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from tapesift.media.types import AudioChunk
from tapesift.schema.records import Utterance


class VAD(Protocol):
    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]:
        """Speech regions of one chunk as (start_s, end_s) on the container clock: sorted,
        non-overlapping, inside [chunk.start_s, chunk end]. [] when the chunk has no speech."""
        ...


class ASR(Protocol):
    @property
    def id(self) -> str:
        """Backend id for provenance; matches BACKEND_ID_RE."""
        ...

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        """One list per chunk, in order, each sorted by start_s. Chunks are independent: they
        may overlap or leave gaps (the stage's seam handling, R8). Times are on the container
        clock (the backend adds chunk.start_s). Starts are inside the chunk; ends may overshoot
        the chunk end by up to 1.0 s (Whisper rounds segment ends), and the stage clamps (R2).
        No VAD gating here. Any exception is a backend failure (R5)."""
        ...
