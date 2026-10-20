"""fetch_pin (spec 25, R4): cache first, allow-listed download, ModelLoadError. No network."""

from pathlib import Path
from typing import Any

import huggingface_hub
import pytest
from huggingface_hub.errors import LocalEntryNotFoundError

from tapesift.config import EMBEDDER, ModelLoadError
from tapesift.hub import fetch_pin

PIN = EMBEDDER


class Recorder:
    """Stands in for snapshot_download: each call pops the next scripted outcome."""

    def __init__(self, tmp_path: Path, *outcomes: Exception | tuple[str, ...]) -> None:
        self.tmp_path = tmp_path
        self.outcomes = list(outcomes)
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        d = self.tmp_path / f"snap{len(self.calls)}"
        for name in outcome:
            f = d / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")
        return str(d)


def _install(monkeypatch: pytest.MonkeyPatch, rec: Recorder) -> None:
    monkeypatch.setattr(huggingface_hub, "snapshot_download", rec)


def test_cached_snapshot_needs_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recorder(tmp_path, PIN.files)
    _install(monkeypatch, rec)
    assert fetch_pin(PIN) == tmp_path / "snap1"
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert (args or (kwargs["repo_id"],))[0] == PIN.repo
    assert kwargs["local_files_only"] is True
    assert kwargs["revision"] == PIN.revision
    assert kwargs["allow_patterns"] == list(PIN.files)


def test_miss_downloads_with_allow_list_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder(tmp_path, LocalEntryNotFoundError("not cached"), PIN.files)
    _install(monkeypatch, rec)
    assert fetch_pin(PIN) == tmp_path / "snap2"
    assert len(rec.calls) == 2
    kwargs = rec.calls[1][1]
    assert kwargs["local_files_only"] is False
    assert kwargs["etag_timeout"] == 10.0
    assert kwargs["revision"] == PIN.revision
    assert kwargs["allow_patterns"] == list(PIN.files)


def test_partial_cache_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recorder(tmp_path, PIN.files[:1], PIN.files)
    _install(monkeypatch, rec)
    assert fetch_pin(PIN) == tmp_path / "snap2"
    assert len(rec.calls) == 2
    assert rec.calls[1][1]["local_files_only"] is False


def test_missing_file_after_download_is_model_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder(tmp_path, LocalEntryNotFoundError("not cached"), ("onnx/model.onnx",))
    _install(monkeypatch, rec)
    with pytest.raises(ModelLoadError) as e:
        fetch_pin(PIN)
    assert str(e.value).endswith("missing tokenizer.json")


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(OSError("offline"), id="OSError"),
        pytest.param(RuntimeError("boom"), id="RuntimeError"),
    ],
)
def test_hub_error_is_model_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    rec = Recorder(tmp_path, LocalEntryNotFoundError("not cached"), exc)
    _install(monkeypatch, rec)
    with pytest.raises(ModelLoadError) as e:
        fetch_pin(PIN)
    assert str(e.value).startswith("cannot fetch BAAI/bge-small-en-v1.5@5c38ec7c405e:")
