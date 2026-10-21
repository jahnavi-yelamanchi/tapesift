"""Whisper phantom phrases on non-speech audio (spec row "Silence or music only", card 2 C).
The project's own short list; no third-party data."""

from __future__ import annotations

from typing import Final

from tapesift.eval.wer import normalize

PHANTOM_PHRASES: Final[tuple[str, ...]] = (
    "Thank you.",
    "Thanks for watching!",  # docs/spec.md row 297
    "Thank you for watching.",
)
MAX_SPEECH_SHARE: Final = 0.5  # a listed phrase is dropped only if VAD covers at most this share

_NORMALIZED: Final = frozenset(normalize(p) for p in PHANTOM_PHRASES)


def is_phantom_text(text: str) -> bool:
    """The WHOLE utterance matches: tapesift.eval.wer.normalize(text) equals a normalized
    PHANTOM_PHRASES entry. No substring match."""
    return normalize(text) in _NORMALIZED
