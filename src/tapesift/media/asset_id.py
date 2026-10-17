"""Stable asset IDs (ADR 0012). Stdlib only."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

SCHEME: Final = "tsid1"  # scheme version; CHUNK_BYTES is part of it
CHUNK_BYTES: Final = 8 * 1024 * 1024  # 8 MiB


def asset_id(path: Path, *, full: bool = False) -> str:
    """Default: "tsid1:" + sha256(8-byte big-endian size || first 8 MiB || last 8 MiB, no
    overlap). full=True: "sha256:" + the plain file sha256, so `shasum -a 256` verifies it.
    Raises OSError if the file can't be read.

    Collision: two files of equal size > 16 MiB with identical first and last 8 MiB share a
    default ID; E7 confirms DUPLICATE with a full hash."""
    size = path.stat().st_size
    with path.open("rb") as f:
        if full:
            return "sha256:" + hashlib.file_digest(f, "sha256").hexdigest()
        h = hashlib.sha256(size.to_bytes(8, "big"))
        h.update(f.read(CHUNK_BYTES))  # head: bytes [0, min(size, 8 MiB))
        f.seek(max(CHUNK_BYTES, size - CHUNK_BYTES))  # tail never overlaps head
        h.update(f.read())  # tail: empty when size <= 8 MiB
        return f"{SCHEME}:" + h.hexdigest()
