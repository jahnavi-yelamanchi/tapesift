"""The one place that fetches model files (R4). Imports huggingface_hub inside fetch_pin only."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tapesift.config import ModelLoadError, ModelPin

HUB_ETAG_TIMEOUT_S: Final = 10.0  # per metadata request; each file read also times out after
# huggingface_hub's HF_HUB_DOWNLOAD_TIMEOUT (default 10 s)


def fetch_pin(pin: ModelPin) -> Path:
    """Local snapshot directory holding every name in pin.files at pin.revision."""
    import huggingface_hub
    from huggingface_hub.errors import LocalEntryNotFoundError

    allow = list(pin.files)
    where = f"{pin.repo}@{pin.revision[:12]}"
    try:
        d = Path(
            huggingface_hub.snapshot_download(  # pyright: ignore[reportUnknownMemberType]
                pin.repo, revision=pin.revision, allow_patterns=allow, local_files_only=True
            )
        )
        if all((d / name).exists() for name in pin.files):
            return d
    except LocalEntryNotFoundError:
        pass
    try:
        d = Path(
            huggingface_hub.snapshot_download(  # pyright: ignore[reportUnknownMemberType]
                pin.repo,
                revision=pin.revision,
                allow_patterns=allow,
                local_files_only=False,
                etag_timeout=HUB_ETAG_TIMEOUT_S,
            )
        )
    except Exception as e:  # any hub, network or OS failure is a load failure
        raise ModelLoadError(f"cannot fetch {where}: {type(e).__name__}: {e}") from e
    for name in pin.files:
        if not (d / name).exists():
            raise ModelLoadError(f"{where}: missing {name}")
    return d
