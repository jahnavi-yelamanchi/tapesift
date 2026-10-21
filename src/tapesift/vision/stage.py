"""Caption stage (E4): sample frames, caption them in bounded batches, flag on-screen text.
Imports neither torch nor PIL (M1 R6)."""

from __future__ import annotations

import logging
import time

from tapesift.config import Config, vlm_max_batch
from tapesift.media.types import AssetInfo, Decoder, Frame
from tapesift.schema.records import Caption
from tapesift.vision.types import VLM
from tapesift.warning_codes import AssetWarning, WarningCode, WarningSink

log = logging.getLogger(__name__)


def caption_asset(
    asset: AssetInfo, decoder: Decoder, vlm: VLM, cfg: Config, *, warn: WarningSink
) -> list[Caption]:
    """One caption per frame of decoder.iter_frames(asset, 1 / cfg.sampling.fixed_fps,
    warn=warn), in batches of at most vlm_max_batch(cfg), prompt cfg.vlm.prompt. [] when
    asset.video is None. MEDIA_TEXT via warn when any caption has media_text."""
    if asset.video is None:
        return []
    extra = {"asset_id": asset.id, "stage": "caption"}
    max_batch = vlm_max_batch(cfg)
    captions: list[Caption] = []
    batches = 0
    spent = 0.0

    def flush(part: list[Frame]) -> None:
        nonlocal batches, spent
        t0 = time.perf_counter()
        caps = vlm.caption(part, cfg.vlm.prompt)
        spent += time.perf_counter() - t0
        if len(caps) != len(part):
            raise ValueError(f"VLM returned {len(caps)} captions for {len(part)} frames")
        if any(c.t_s != f.t_s for c, f in zip(caps, part, strict=True)):
            raise ValueError("VLM caption t_s differs from its frame")
        captions.extend(caps)
        batches += 1

    buf: list[Frame] = []
    for frame in decoder.iter_frames(asset, 1 / cfg.sampling.fixed_fps, warn=warn):
        buf.append(frame)
        if len(buf) == max_batch:
            flush(buf)
            buf = []
    if buf:
        flush(buf)

    if not captions:
        log.info("captioned 0 frames", extra=extra)
        return []
    log.info(
        "captioned %d frames in %d batches, %.2f s/frame",
        len(captions),
        batches,
        spent / len(captions),
        extra=extra,
    )
    n = sum(1 for c in captions if c.media_text)
    if n:
        warn(
            AssetWarning(
                WarningCode.MEDIA_TEXT,
                f"on-screen text in {n} of {len(captions)} sampled frames; "
                "stored as untrusted media_text",
            )
        )
    return captions
