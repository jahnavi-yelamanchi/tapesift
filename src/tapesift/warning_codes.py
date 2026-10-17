"""Warning codes from the messy-data table in docs/spec.md, and the error every stage raises.
Imports nothing outside the stdlib."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class WarningCode(StrEnum):
    """Exactly the codes in docs/spec.md, Messy multimodal data. A test keeps them in sync."""

    VFR_DETECTED = "VFR_DETECTED"
    ROTATED = "ROTATED"
    START_OFFSET = "START_OFFSET"
    AV_LENGTH_MISMATCH = "AV_LENGTH_MISMATCH"
    NO_AUDIO = "NO_AUDIO"
    MULTI_AUDIO = "MULTI_AUDIO"
    LOW_SPEECH = "LOW_SPEECH"
    PARTIAL_DECODE = "PARTIAL_DECODE"  # some output was produced, some was lost
    UNREADABLE = "UNREADABLE"  # not media, or cannot be opened at all
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    INTERLACED = "INTERLACED"
    CROPPED = "CROPPED"
    HDR_CONVERTED = "HDR_CONVERTED"
    SHORT_CLIP = "SHORT_CLIP"
    DOWNSCALED = "DOWNSCALED"
    DUPLICATE = "DUPLICATE"
    MEDIA_TEXT = "MEDIA_TEXT"


@dataclass(frozen=True, slots=True)
class AssetWarning:
    """One entry of the output schema's `warnings` list: {"code": ..., "detail": ...}."""

    code: WarningCode
    detail: str  # human-readable, names the cause, e.g. "video stream 0: undecodable 2.75-5.00 s"

    def __post_init__(self) -> None:
        # pyright already rejects a plain str; this catches untyped callers at runtime.
        if not isinstance(self.code, WarningCode):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"code must be a WarningCode, got {self.code!r}")


WarningSink = Callable[[AssetWarning], None]
"""Where streaming stages report non-fatal warnings. Callers usually pass `some_list.append`.
If the sink raises, the exception propagates out of the iterator; stages never catch it."""


class StageError(Exception):
    """Base for every stage's per-file failure. The runner catches this, records `.warning`
    on the asset, and moves to the next file. Picklable, so it crosses worker processes.
    Programmer errors (bad arguments) raise ValueError instead and are not caught per file.
    Subclasses must keep the (code, detail) __init__ signature so pickling works."""

    allowed: ClassVar[frozenset[WarningCode] | None] = None  # codes a subclass may carry; None: any

    def __init__(self, code: WarningCode, detail: str) -> None:
        if self.allowed is not None and code not in self.allowed:
            raise ValueError(f"{type(self).__name__} cannot carry {code}")
        super().__init__(code, detail)  # args=(code, detail) keeps pickle working
        self.warning = AssetWarning(code, detail)

    def __str__(self) -> str:
        return f"{self.warning.code}: {self.warning.detail}"
