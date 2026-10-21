"""Test support for the E7 runner (docs/specs/30-runner.md, "Test support"). Module-level, so a
spawned worker can import `Load` functions from here by name. Fakes only (ADR 0008)."""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import TYPE_CHECKING

from tests.fakes import FakeEmbedder, MemoryStore

from tapesift import __version__
from tapesift.config import Config, ModelLoadError
from tapesift.media.types import AssetInfo
from tapesift.schema.records import AssetRecord, Provenance

if TYPE_CHECKING:
    from tapesift.runner.run import Analyze, Beat, StageSink

SPY_ENV = "TAPESIFT_TEST_SPY"
FAULTS_ENV = "TAPESIFT_TEST_FAULTS"

SIX = (
    "clean.mp4",
    "speech.mp4",
    "vfr.mp4",
    "no_audio.mp4",
    "short_clip.mp4",
    "rotated_270.mp4",
)
"""Six distinct IDs. Tests copy them into `tmp_path / "in"` as a.mp4 to f.mp4, in this order."""


def _spy_append(text: str) -> None:
    spy = os.environ.get(SPY_ENV)
    if spy:
        with Path(spy).open("a", encoding="utf-8") as f:
            f.write(text)


def _faults() -> dict[str, str]:
    raw = os.environ.get(FAULTS_ENV, "")
    return dict(item.split(":", 1) for item in raw.split(",") if item)


def _inject(fault: str, asset: AssetInfo, beat: Beat) -> None:
    if fault == "boom":
        raise RuntimeError("boom")
    if fault in ("stuck", "slow"):
        time.sleep(300)
    elif fault == "beating":
        for _ in range(15):  # 3 s
            beat()
            time.sleep(0.2)
    elif fault == "crash":
        os._exit(3)
    elif fault == "killparent":
        os.kill(os.getppid(), signal.SIGKILL)
        time.sleep(300)
    elif fault == "log":
        logging.getLogger("tapesift.test").warning(
            "hello", extra={"asset_id": asset.id, "stage": "asr"}
        )
    elif fault == "print":
        print("noise")  # noqa: T201 (the fault under test is a stray print)
    else:
        raise ValueError(f"unknown test fault {fault!r}")


def quick(cfg: Config) -> Analyze:
    """No decoding. Spy file: `pid:<pid>` at load, then one file-name line per analysis."""
    _spy_append(f"pid:{os.getpid()}\n")

    def analyze(asset: AssetInfo, on_stage: StageSink, beat: Beat) -> AssetRecord:
        on_stage("asr")
        _spy_append(asset.path.name + "\n")
        fault = _faults().get(asset.path.name)
        if fault is not None:
            _inject(fault, asset, beat)
        return AssetRecord(asset, (), (), (), Provenance(__version__, None, None, None))

    return analyze


def fake_pipeline(cfg: Config) -> Analyze:
    """The real E7 pipeline (PyAV, E3, E4) over fake models. Same spy lines as `quick`. Pipeline
    imports are local, so this module imports before tapesift.pipeline.index exists."""
    import functools

    from tests.fakes import FakeASR, FakeVAD, FakeVLM

    from tapesift.media.decode import PyAVDecoder
    from tapesift.pipeline.index import Backends, index_asset

    _spy_append(f"pid:{os.getpid()}\n")
    backends = Backends(
        PyAVDecoder(),
        FakeVAD(),
        FakeASR(),
        FakeVLM() if cfg.vlm.backend == "transformers" else None,
    )
    inner = functools.partial(index_asset, backends=backends, cfg=cfg)

    def analyze(asset: AssetInfo, on_stage: StageSink, beat: Beat) -> AssetRecord:
        _spy_append(asset.path.name + "\n")
        return inner(asset, on_stage, beat)

    return analyze


def broken(cfg: Config) -> Analyze:
    raise ModelLoadError("fake: no model")


def dies(cfg: Config) -> Analyze:
    os._exit(3)


def slowload(cfg: Config) -> Analyze:
    time.sleep(300)
    raise AssertionError("unreachable")


class SpyStore(MemoryStore):
    """Records asset IDs it was given; `fail_on[file name]` is raised from `upsert`."""

    def __init__(self) -> None:
        super().__init__(FakeEmbedder())
        self.upserts: list[str] = []
        self.deletes: list[str] = []
        self.fail_on: dict[str, BaseException] = {}
        self._upserting = False

    def upsert(self, record: AssetRecord) -> None:
        err = self.fail_on.get(Path(record.asset.path).name)
        if err is not None:
            raise err
        self._upserting = True  # MemoryStore.upsert calls self.delete; that is not a runner delete
        try:
            super().upsert(record)
        finally:
            self._upserting = False
        self.upserts.append(record.asset.id)

    def delete(self, asset_id: str) -> None:
        super().delete(asset_id)
        if not self._upserting:
            self.deletes.append(asset_id)
