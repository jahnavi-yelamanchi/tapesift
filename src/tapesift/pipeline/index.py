"""Per-asset glue (spec 732: cli -> pipeline -> stages): resolve the config (R9), build the
worker's backends, and turn one AssetInfo into one AssetRecord (R5). Real backend modules are
imported inside the functions that build them (R6)."""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tapesift import __version__
from tapesift.audio.stage import transcribe_asset
from tapesift.audio.types import ASR, VAD
from tapesift.cli.doctor import Probes, diagnose
from tapesift.config import Config, ModelLoadError, vision_available
from tapesift.media.types import AssetInfo, AudioChunk, Decoder, Frame
from tapesift.runner.run import Analyze, Beat, StageSink
from tapesift.schema.records import AssetRecord, Caption, Provenance, Utterance
from tapesift.store.types import Store
from tapesift.vision.stage import caption_asset  # E4: the one import site
from tapesift.vision.types import VLM
from tapesift.warning_codes import AssetWarning, StageError, WarningCode, WarningSink

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Backends:
    decoder: Decoder
    vad: VAD
    asr: ASR
    vlm: VLM | None  # None: captions off (R9)


def resolve_config(cfg: Config, *, probes: Probes | None = None) -> Config:
    """Fill the profile (doctor's pick) and resolve vlm.backend "auto" (R9). ModelLoadError when
    vlm.backend = "transformers" but the vision extra is missing."""
    update: dict[str, object] = {}
    if cfg.profile is None:
        update["profile"] = diagnose(probes or Probes(), Path.cwd(), __version__).profile
    backend = cfg.vlm.backend
    if backend == "auto":
        if vision_available():
            backend = "transformers"
        else:
            log.warning('captions off: install "tapesift[vision]"')
            backend = "none"
    elif backend == "transformers" and not vision_available():
        raise ModelLoadError(
            'vlm.backend = "transformers" needs the vision extra: install "tapesift[vision]"'
        )
    elif backend == "none":
        log.info('captions off (vlm.backend = "none")')
    if backend != cfg.vlm.backend:
        update["vlm"] = cfg.vlm.model_copy(update={"backend": backend})
    return cfg.model_copy(update=update)


def load_backends(cfg: Config) -> Backends:
    """Real backends. Runs in the worker only."""
    from tapesift.audio.faster_whisper import FasterWhisperASR
    from tapesift.audio.vad import SileroVAD
    from tapesift.media.decode import PyAVDecoder

    vlm: VLM | None = None
    if cfg.vlm.backend == "transformers":
        from tapesift.vision.transformers_vlm import TransformersVLM

        vlm = TransformersVLM(cfg)
    return Backends(PyAVDecoder(), SileroVAD(cfg), FasterWhisperASR(cfg), vlm)


class _BeatingDecoder:
    """Calls beat() before yielding each frame or chunk, so a stuck read stops the beats."""

    def __init__(self, inner: Decoder, beat: Beat) -> None:
        self._inner, self._beat = inner, beat

    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        for frame in self._inner.iter_frames(asset, every_s, warn=warn):
            self._beat()
            yield frame

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        for chunk in self._inner.iter_audio(
            asset, sample_rate, track=track, chunk_s=chunk_s, warn=warn
        ):
            self._beat()
            yield chunk


def index_asset(
    asset: AssetInfo, on_stage: StageSink, beat: Beat, *, backends: Backends, cfg: Config
) -> AssetRecord:
    """One asset to one record. A StageError degrades that stage (its warning goes on the
    record); any other exception propagates and the runner fails the asset at the last stage."""
    decoder = _BeatingDecoder(backends.decoder, beat)
    warnings: list[AssetWarning] = []
    utterances: list[Utterance] = []
    captions: list[Caption] = []
    asr_id = vlm_id = prompt = None

    on_stage("asr")
    if asset.audio:
        try:
            utterances = transcribe_asset(
                asset, decoder, backends.vad, backends.asr, cfg, warn=warnings.append
            )
            if not any(w.code is WarningCode.LOW_SPEECH for w in warnings):
                asr_id = backends.asr.id
        except StageError as e:
            warnings.append(e.warning)

    on_stage("vlm")
    if asset.video is not None and backends.vlm is not None:
        try:
            captions = caption_asset(asset, decoder, backends.vlm, cfg, warn=warnings.append)
            vlm_id, prompt = backends.vlm.id, cfg.vlm.prompt
        except StageError as e:
            warnings.append(e.warning)

    on_stage("record")
    return AssetRecord(
        asset,
        tuple(utterances),
        tuple(captions),
        tuple(warnings),
        Provenance(__version__, asr_id, vlm_id, prompt),
    )


def load(cfg: Config) -> Analyze:
    """The runner's Load: builds the models once per worker."""
    return functools.partial(index_asset, backends=load_backends(cfg), cfg=cfg)


def open_store(cfg: Config) -> Store:
    """LanceStore(cfg, OnnxEmbedder(cfg)). Runs in the parent only."""
    from tapesift.store.lance import LanceStore
    from tapesift.vision.embed import OnnxEmbedder

    return LanceStore(cfg, OnnxEmbedder(cfg))
