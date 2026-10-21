"""E5: AssetRecord to schema 1.0 JSON (docs/spec.md, Output schema; docs/specs/28-schema.md).
The JSON Schema is asset-1.0.schema.json next to this file, shipped as package data; tests
validate against it (jsonschema is a dev dependency only). Imports the stdlib and records only."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import sys
from pathlib import Path
from typing import Final

from tapesift.schema.records import AssetRecord

log = logging.getLogger(__name__)

SCHEMA_VERSION: Final = "1.0"


def _f(x: float | None) -> float | None:
    """A builtin float: numpy scalars from backends become float, and + 0.0 turns -0.0 into 0.0."""
    return None if x is None else float(x) + 0.0


def to_json(record: AssetRecord) -> dict[str, object]:
    """Schema 1.0 as plain JSON types in schema key order (docs/specs/28-schema.md, Mapper)."""
    a, p = record.asset, record.provenance
    v, da = a.video, a.default_audio
    video = v and {
        "codec": v.codec,
        "w": v.w,
        "h": v.h,
        "fps_avg": _f(v.fps_avg),
        "vfr": v.vfr,
        "rotation": v.rotation,
    }
    audio = da and {"codec": da.codec, "tracks": len(a.audio), "lang": da.lang}
    return {
        "schema_version": SCHEMA_VERSION,
        "asset": {
            "id": a.id,
            "path": str(a.path),
            "duration_s": _f(a.duration_s),
            "video": video,
            "audio": audio,
            "license": None,
        },
        "shots": [],
        "utterances": [
            {
                "start_s": _f(u.start_s),
                "end_s": _f(u.end_s),
                "text": u.text,
                "lang": u.lang,
                "conf": _f(u.conf),
                "words": [
                    {"w": w.w, "start_s": _f(w.start_s), "end_s": _f(w.end_s)} for w in u.words
                ],
            }
            for u in record.utterances
        ],
        "captions": [
            {
                "t_s": _f(c.t_s),
                "shot": None,
                "text": c.text,
                "conf": _f(c.conf),
                "media_text": list(c.media_text),
            }
            for c in record.captions
        ],
        "warnings": [{"code": w.code.value, "detail": w.detail} for w in record.warnings],
        "provenance": {"tapesift": p.tapesift, "asr": p.asr, "vlm": p.vlm, "prompt": p.prompt},
    }


def _sync(fd: int) -> None:
    """Flush fd to stable storage; on macOS fsync leaves data in the drive cache (F_FULLFSYNC)."""
    if sys.platform == "darwin":
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:  # ENOTSUP on network and FUSE mounts: plain fsync is the best there is
            pass
    os.fsync(fd)


def write_json(record: AssetRecord, path: Path) -> None:
    """Write to_json(record) to path atomically and durably. The bytes go to .tapesift-<pid>.tmp
    in path's folder, are flushed to disk (_sync), then renamed over path, so a reader sees the
    old file or the new one, never a part; then the folder is synced so the rename survives a
    power cut. A folder that cannot be synced (some network filesystems) is logged at WARNING,
    not raised: the file is already in place. A symlink at path is replaced, never followed;
    the temp file is created with O_EXCL|O_NOFOLLOW, so a planted link there is never followed.
    UTF-8, 2-space indent, one trailing newline; same record, same bytes. Each lone surrogate in
    any string (an undecodable file name, or a detail quoting one) is written as "?", so two such
    names can look alike; asset.id stays the key. NaN or infinity raises ValueError before any
    file is touched. The folder must exist. On any other failure the temp file is removed, path
    is unchanged, and the exception propagates (M1 R5: the asset fails, the batch goes on). One
    writer per process: two threads writing into one folder at once would share the temp name."""
    data = json.dumps(to_json(record), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    tmp = path.with_name(f".tapesift-{os.getpid()}.tmp")
    try:
        tmp.unlink(missing_ok=True)  # a stale or planted entry; unlink never follows a symlink
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        with os.fdopen(os.open(tmp, flags, 0o666), "wb") as f:
            f.write(data.encode("utf-8", "replace"))
            f.flush()
            _sync(f.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            _sync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        log.warning("wrote %s but could not sync its folder: %s", path.name, e)
