"""The one place that opens media for demuxing (#21, docs/specs/21-safe-opener.md).
The file is checked as a regular file, opened once, and handed to FFmpeg as a descriptor
(`fd` protocol only), with only the allowed container formats. So a crafted file (concat list,
playlist, image sequence, mov dref) cannot make FFmpeg read another file or the network.
Nothing else in tapesift calls av.open."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Final

import av
import av.error

if TYPE_CHECKING:
    from av.container import InputContainer

# Demuxer names as FFmpeg reports them; the whitelist matches any name in a comma list.
ALLOWED_FORMATS: Final = ("mov", "matroska", "avi", "mpegts", "wav", "mp3", "aac", "flac", "ogg")
OPEN_TIMEOUT_S: Final = 30.0  # per open and per demux call; module constant until config.py exists


class UnsafeInputError(OSError):
    """open_media refused the file: not a regular file, or a container format FFmpeg may not
    demux here. An OSError, so every stage's `except (FFmpegError, OSError)` maps it to
    UNREADABLE unchanged."""


def _kind(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISCHR(mode):
        return "character device"
    if stat.S_ISBLK(mode):
        return "block device"
    if stat.S_ISSOCK(mode):
        return "socket"
    return "unknown type"


def open_media(path: Path) -> InputContainer:
    """Open one local media file for demuxing. Every stage calls this; nothing else calls av.open.
    Raises UnsafeInputError, OSError (missing, permission) or av.error.FFmpegError (not media).
    Never blocks on a FIFO."""
    mode = os.stat(path).st_mode  # noqa: PTH116  # follows symlinks; target must be regular
    if not stat.S_ISREG(mode):
        raise UnsafeInputError(f"not a regular file: {_kind(mode)}")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)  # O_NONBLOCK: a swapped-in FIFO can't block
    try:
        mode = os.fstat(fd).st_mode  # catches a swap between stat and open
        if not stat.S_ISREG(mode):
            raise UnsafeInputError(f"not a regular file: {_kind(mode)}")
        os.set_blocking(fd, True)
        # FFmpeg dups the fd, so closing ours below is safe. Never add options (e.g.
        # enable_drefs, use_absolute_path) without a decision card.
        return av.open(
            "fd:",
            options={
                "protocol_whitelist": "fd",
                "format_whitelist": ",".join(ALLOWED_FORMATS),
                "fd": str(fd),
            },
            timeout=OPEN_TIMEOUT_S,
        )
    except av.error.ArgumentError as e:  # FFmpeg's answer to a demuxer not on the whitelist
        raise UnsafeInputError("container format not allowed or header invalid") from e
    finally:
        os.close(fd)
