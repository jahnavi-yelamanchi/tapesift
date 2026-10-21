"""The end-of-run summary of `tapesift index`: per-file results, counts, the exit code, the
human text (stderr) and the --json document (card 6). Pure: no I/O."""

from __future__ import annotations

import signal
from dataclasses import dataclass
from typing import Final, Literal, get_args

from tapesift.warning_codes import WarningCode

Status = Literal[
    "indexed", "pending", "skipped", "duplicate", "failed", "failed_before", "deferred"
]
STATUSES: Final[tuple[Status, ...]] = get_args(Status)  # this order, everywhere


@dataclass(frozen=True, slots=True)
class FileResult:
    path: str  # absolute (card 5); display form: undecodable bytes as backslash escapes
    status: Status
    asset_id: str | None  # None when the file was not probed or probe failed
    duration_s: float | None  # AssetInfo.duration_s; feeds media_hours; not in --json
    code: WarningCode | None = None  # UNREADABLE (probe-phase failures), DUPLICATE
    stage: str | None = None  # failed: the stage that failed (a StageName)
    detail: str | None = None  # the exact reason, e.g. "same content as /a/clean.mp4"


@dataclass(frozen=True, slots=True)
class Summary:
    out_dir: str  # os.path.abspath(cfg.out_dir)
    id_mode: Literal["tsid1", "sha256"]
    dry_run: bool
    interrupted_by: int | None  # the signal number (SIGINT, SIGTERM, SIGHUP); None: ran to the end
    max_media_hours: float | None
    total: int  # entries the walk produced; len(files) < total only when interrupted
    files: tuple[FileResult, ...]  # walk order
    aborted: str | None = None  # "abandoned_workers": the run stopped early (RunAborted)

    @property
    def interrupted(self) -> bool:
        return self.interrupted_by is not None

    def counts(self) -> dict[Status, int]:
        return {s: sum(r.status == s for r in self.files) for s in STATUSES}

    def media_hours(self) -> float:
        counted = "pending" if self.dry_run else "indexed"
        return sum((r.duration_s or 0.0) for r in self.files if r.status == counted) / 3600

    @property
    def exit_code(self) -> int:
        """1 if any failed or failed_before, else 0 (R5); interrupted is the CLI's."""
        return int(any(r.status in ("failed", "failed_before") for r in self.files))


def to_dict(summary: Summary) -> dict[str, object]:
    return {
        "version": 1,
        "out_dir": summary.out_dir,
        "id_mode": summary.id_mode,
        "dry_run": summary.dry_run,
        "interrupted": summary.interrupted,
        **({"aborted": summary.aborted} if summary.aborted else {}),  # only on an abort
        "max_media_hours": summary.max_media_hours,
        "total": summary.total,
        "counts": summary.counts(),
        "media_hours": round(summary.media_hours(), 4),
        "files": [
            {
                "path": r.path,
                "status": r.status,
                "asset_id": r.asset_id,
                "code": r.code.value if r.code else None,
                "stage": r.stage,
                "detail": r.detail,
            }
            for r in summary.files
        ],
    }


def render(summary: Summary) -> str:
    c, h = summary.counts(), summary.media_hours()
    if summary.dry_run:
        lines = [
            f"dry run, nothing written: {c['pending']} to index ({h:.2f} h of media), "
            f"skipped {c['skipped']}, duplicate {c['duplicate']}, failed {c['failed']}, "
            f"failed before {c['failed_before']}, deferred {c['deferred']} "
            f"({summary.total} files)"
        ]
    else:
        lines = [
            f"indexed {c['indexed']}, skipped {c['skipped']}, duplicate {c['duplicate']}, "
            f"failed {c['failed']}, failed before {c['failed_before']}, "
            f"deferred {c['deferred']} ({summary.total} files, {h:.2f} h of media)"
        ]
    for status, header in (
        ("failed", "failed:"),
        ("failed_before", "failed before:"),
        ("duplicate", "duplicate:"),
    ):
        rows = [r for r in summary.files if r.status == status]
        if not rows:
            continue
        lines.append(header)
        lines += [
            f"  {r.path}{f' ({r.stage})' if r.stage else ''}: "
            f"{f'{r.code} ' if r.code else ''}{r.detail}"
            for r in rows
        ]
        if status == "failed_before":
            lines.append(f"  to retry, delete their markers in {summary.out_dir}/failed/")
    if c["deferred"] > 0:
        lines.append(
            f"stopped by --max-media-hours {summary.max_media_hours:g}: "
            f"{c['deferred']} files left for the next run"
        )
    if summary.interrupted_by is not None:
        lines.append(
            f"interrupted by {signal.Signals(summary.interrupted_by).name} after "
            f"{len(summary.files)} of {summary.total} files; rerun to resume"
        )
    return "\n".join(lines)
