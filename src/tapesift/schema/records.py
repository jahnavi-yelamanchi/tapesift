"""Result records shared by the stages (E3, E4), the schema mapper (E5), the store (E6) and the
runner (E7). Frozen stdlib dataclasses (M0 card); E5 maps them to schema 1.0 JSON. Rules: M1
R1-R3. Imports nothing heavier than tapesift.media.types (numpy)."""

from __future__ import annotations

import dataclasses
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Final, Literal

from tapesift.media.types import AssetInfo
from tapesift.warning_codes import AssetWarning

BACKEND_ID_RE: Final = re.compile(r"[a-z0-9-]+:[^\s@]+@(?:[0-9a-f]{40}|unpinned)")
"""Use with fullmatch. "<backend>:<model>@<revision>" (card 6). The revision is the full 40-hex
commit SHA, or exactly "unpinned" for an endpoint backend that reports none."""


def _check_span(what: str, start_s: float, end_s: float) -> None:
    if not (math.isfinite(start_s) and math.isfinite(end_s) and 0.0 <= start_s <= end_s):
        raise ValueError(f"{what}: need finite 0 <= start_s <= end_s, got {start_s}, {end_s}")


def _check_conf(what: str, conf: float) -> None:
    if not 0.0 <= conf <= 1.0:  # also rejects NaN
        raise ValueError(f"{what}: conf must be in [0, 1], got {conf}")


@dataclass(frozen=True, slots=True)
class Word:
    """schema: utterances[].words[] = {"w", "start_s", "end_s"}."""

    w: str
    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        _check_span("Word", self.start_s, self.end_s)


@dataclass(frozen=True, slots=True)
class Utterance:
    """schema: utterances[]. Times are seconds on the container clock (M0 R1)."""

    start_s: float
    end_s: float
    text: str
    lang: str | None  # ISO 639-1 code the ASR detected, e.g. "en"; None if none (card 5)
    conf: float  # in [0, 1]; how it is derived is E3's spec
    words: tuple[Word, ...]  # sorted by start_s, each inside [start_s, end_s]; may be empty

    def __post_init__(self) -> None:
        _check_span("Utterance", self.start_s, self.end_s)
        _check_conf("Utterance", self.conf)
        starts = [w.start_s for w in self.words]
        if starts != sorted(starts) or any(
            w.start_s < self.start_s or w.end_s > self.end_s for w in self.words
        ):
            raise ValueError("Utterance.words must be sorted and inside the utterance")


@dataclass(frozen=True, slots=True)
class Caption:
    """schema: captions[]. No `shot` field: E5 writes "shot": null in v0.1 (card 2)."""

    t_s: float  # the captioned Frame's t_s
    text: str
    conf: float | None  # in [0, 1]; None when the backend cannot compute one (card 2)
    media_text: tuple[str, ...]  # words the VLM read in the frame; untrusted (spec Y1)

    def __post_init__(self) -> None:
        _check_span("Caption", self.t_s, self.t_s)
        if self.conf is not None:
            _check_conf("Caption", self.conf)


@dataclass(frozen=True, slots=True)
class Provenance:
    """schema: provenance. A stage that did not run has None (card 6)."""

    tapesift: str  # tapesift.__version__
    asr: str | None  # ASR.id; None when ASR did not run (no audio, LOW_SPEECH, StageError)
    vlm: str | None  # VLM.id; None when captioning did not run (no video, captions off, ...)
    prompt: str | None  # prompt id, e.g. "caption_v1"; set exactly when vlm is set

    def __post_init__(self) -> None:
        for name, value in (("asr", self.asr), ("vlm", self.vlm)):
            if value is not None and not BACKEND_ID_RE.fullmatch(value):
                raise ValueError(f"Provenance.{name} is not a backend id: {value!r}")
        if (self.vlm is None) != (self.prompt is None):
            raise ValueError("Provenance.vlm and Provenance.prompt are set together")


@dataclass(frozen=True, slots=True)
class AssetRecord:
    """Everything known about one asset: what E5 serializes, E6 indexes and E7 writes.
    Strict on purpose: stages clamp first (R2), so a raise here is a programmer bug."""

    asset: AssetInfo
    utterances: tuple[Utterance, ...]  # sorted by start_s
    captions: tuple[Caption, ...]  # t_s strictly increasing
    warnings: tuple[AssetWarning, ...]  # normalized on construction: union with asset.warnings,
    # deduplicated, sorted by (code, detail)
    provenance: Provenance

    def __post_init__(self) -> None:
        merged = set(self.warnings) | set(self.asset.warnings)
        object.__setattr__(
            self, "warnings", tuple(sorted(merged, key=lambda w: (w.code.value, w.detail)))
        )
        starts = [u.start_s for u in self.utterances]
        times = [c.t_s for c in self.captions]
        if starts != sorted(starts) or any(b <= a for a, b in pairwise(times)):
            raise ValueError("AssetRecord: utterances sorted, caption t_s strictly increasing")
        d = self.asset.duration_s
        if d is not None and (
            any(u.end_s > d for u in self.utterances) or any(c.t_s >= d for c in self.captions)
        ):
            raise ValueError(f"AssetRecord: a time is past duration_s {d}")


def clamp_utterance(u: Utterance, lo: float, hi: float) -> Utterance | None:
    """Fit an ASR utterance into [lo, hi] (R2): the stage passes lo = the chunk start and
    hi = min(chunk end, duration_s). None when nothing is left (u.start_s >= hi or u.end_s < lo).
    Otherwise start = clamp(u.start_s), end = clamp(max(u.end_s, start)), and each word is clamped
    into [start, end] the same way; a word with w.start_s >= hi or w.end_s < lo is dropped.
    Never raises on overshoot; ValueError only when lo, hi are not finite with 0 <= lo <= hi."""

    _check_span("clamp_utterance bounds", lo, hi)

    def c(t: float, a: float, b: float) -> float:
        return min(max(t, a), b)

    if u.start_s >= hi or u.end_s < lo:
        return None
    s = c(u.start_s, lo, hi)
    e = c(u.end_s, s, hi)
    words = tuple(
        Word(w.w, ws := c(w.start_s, s, e), c(w.end_s, ws, e))
        for w in u.words
        if w.start_s < hi and w.end_s >= lo
    )
    return dataclasses.replace(u, start_s=s, end_s=e, words=words)


class Modality(StrEnum):
    """What a search hit matched. The CLI's --modality any is modality=None. Consumers of
    --json must tolerate values added later (card 3)."""

    SPEECH = "speech"  # an utterance
    VISUAL = "visual"  # a caption


@dataclass(frozen=True, slots=True)
class Hit:
    """One search result (card 3). `tapesift search --json` prints
    {"query": <q>, "hits": [dataclasses.asdict(h) for h in hits]}."""

    asset_id: str
    path: str  # str(AssetInfo.path) as indexed
    start_s: float
    end_s: float  # == start_s for VISUAL: a caption is a point in time
    modality: Modality
    text: str  # the utterance text, or the caption text (never the on-screen words)
    media_text: tuple[str, ...]  # VISUAL: the caption's on-screen words; SPEECH: ()
    score: float  # higher is better within one query; never compare across queries (v0.1: cosine)
    trust: Literal["untrusted_media"] = "untrusted_media"  # every hit is media text (Y1, S8)
