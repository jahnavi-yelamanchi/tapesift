"""Deterministic fake backends (docs/specs/25-m1-interfaces.md, "Fakes"). numpy and stdlib only,
so no test loads a real model (ADR 0008). Each fake satisfies its Protocol under pyright."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

# Each block below is its own isort section: the new interface modules do not exist yet, and ruff
# groups a missing module as third-party until they do. This order is valid before and after.
# isort: split
from tapesift.media.types import AudioChunk, Frame

# isort: split
from tapesift.schema.records import AssetRecord, Caption, Hit, Modality, Utterance, Word
from tapesift.vision.types import Embedder

_VOICED_RMS = 0.01
_MIN_CV = 0.5  # std / mean of the frame RMS; speech is bursty, tones and chords are flat
_MERGE_GAP_S = 0.3


class FakeVAD:
    """Energy-envelope VAD. Pinned to the fixture audio by docs/specs/25-m1-interfaces.md."""

    def speech_spans(self, chunk: AudioChunk) -> list[tuple[float, float]]:
        n = chunk.sample_rate // 50
        nf = len(chunk.samples) // n
        if nf < 1:
            return []
        frames = chunk.samples[: nf * n].astype(np.float64).reshape(nf, n)
        r = np.sqrt((frames**2).mean(axis=1))
        if r.max() < _VOICED_RMS or r.std() / r.mean() < _MIN_CV:
            return []
        spans: list[tuple[float, float]] = []
        for i in np.flatnonzero(r >= _VOICED_RMS):
            s = chunk.start_s + int(i) * n / chunk.sample_rate
            e = chunk.start_s + (int(i) + 1) * n / chunk.sample_rate
            if spans and s - spans[-1][1] < _MERGE_GAP_S:
                spans[-1] = (spans[-1][0], e)
            else:
                spans.append((s, e))
        return spans


class FakeASR:
    """One two-word utterance per FakeVAD span. `overshoot_s` imitates Whisper's end rounding."""

    id = "fake:asr@" + "0" * 40

    def __init__(self, overshoot_s: float = 0.0) -> None:
        self.overshoot_s = overshoot_s
        self.calls: list[int] = []
        self._vad = FakeVAD()

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[list[Utterance]]:
        self.calls.append(len(chunks))
        out: list[list[Utterance]] = []
        for chunk in chunks:
            utterances: list[Utterance] = []
            for s, e in self._vad.speech_spans(chunk):
                m = (s + e) / 2
                e2 = e + self.overshoot_s
                words = (Word("fake", s, m), Word("speech", m, e2))
                utterances.append(Utterance(s, e2, "fake speech", "en", 1.0, words))
            out.append(utterances)
        return out


class FakeVLM:
    id = "fake:vlm@" + "0" * 40

    def __init__(self) -> None:
        self.calls: list[int] = []

    def caption(self, frames: Sequence[Frame], prompt_id: str) -> list[Caption]:
        if prompt_id != "caption_v1":
            raise ValueError(f"unknown prompt_id {prompt_id!r}")
        self.calls.append(len(frames))
        return [
            Caption(f.t_s, f"fake caption {f.pixels.shape[1]}x{f.pixels.shape[0]}", 1.0, ())
            for f in frames
        ]


class FakeEmbedder:
    """Hashed bag of words, L2-normalized. `kind` is accepted and ignored."""

    id = "fake:embedder@" + "0" * 40

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.calls: list[int] = []

    def embed_text(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "passage"],
    ) -> NDArray[np.float32]:
        self.calls.append(len(texts))
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok in re.findall(r"[a-z0-9]+", text.lower())[:512]:
                digest = hashlib.blake2b(tok.encode(), digest_size=4).digest()
                out[row, int.from_bytes(digest, "big") % self.dim] += 1.0
            if not out[row].any():
                out[row, 0] = 1.0
            out[row] /= np.linalg.norm(out[row])
        return out


@dataclass(frozen=True, slots=True, eq=False)
class _Row:
    asset_id: str
    path: str
    modality: Modality
    start_s: float
    end_s: float
    text: str
    media_text: tuple[str, ...]
    vector: NDArray[np.float32]


class MemoryStore:
    """A list of rows, following the Store docstrings in tapesift.store.types."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._rows: list[_Row] = []

    def upsert(self, record: AssetRecord) -> None:
        aid, path = record.asset.id, str(record.asset.path)
        pending = [
            (Modality.SPEECH, u.start_s, u.end_s, u.text, (), u.text) for u in record.utterances
        ] + [
            (Modality.VISUAL, c.t_s, c.t_s, c.text, c.media_text, " ".join((c.text, *c.media_text)))
            for c in record.captions
        ]
        vectors = self._embedder.embed_text([p[5] for p in pending], kind="passage")
        self.delete(aid)
        self._rows += [
            _Row(aid, path, mod, s, e, text, media, vectors[i])
            for i, (mod, s, e, text, media, _) in enumerate(pending)
        ]

    def delete(self, asset_id: str) -> None:
        self._rows = [r for r in self._rows if r.asset_id != asset_id]

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        modality: Modality | None = None,
        asset_id: str | None = None,
    ) -> list[Hit]:
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        rows = [
            r
            for r in self._rows
            if (modality is None or r.modality == modality)
            and (asset_id is None or r.asset_id == asset_id)
        ]
        if not rows:
            return []
        q = self._embedder.embed_text([query], kind="query")[0]
        scored = sorted(
            ((float(r.vector @ q), r) for r in rows),
            key=lambda sr: (-sr[0], sr[1].asset_id, sr[1].start_s),
        )
        return [
            Hit(r.asset_id, r.path, r.start_s, r.end_s, r.modality, r.text, r.media_text, score)
            for score, r in scored[:k]
        ]
