"""E6 golden queries on the real fixtures (docs/specs/29-search.md, "Golden smoke"). Records are
built from E1's probe; `fake` runs on the laptop, `onnx` only in the CI models job (ADR 0008)."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES
from scripts.make_fixtures import BURNED_TEXT
from tests.fakes import FakeEmbedder
from typer.testing import CliRunner

import tapesift
from tapesift.cli import ExitCode, app
from tapesift.config import Config
from tapesift.media.probe import probe
from tapesift.schema.records import AssetRecord, Caption, Provenance, Utterance
from tapesift.store import lance
from tapesift.store.lance import LanceStore
from tapesift.vision.types import Embedder

Z = "0" * 40


def _prov(asr: bool, vlm: bool) -> Provenance:
    return Provenance(
        tapesift.__version__,
        "fake:asr@" + Z if asr else None,
        "fake:vlm@" + Z if vlm else None,
        "caption_v1" if vlm else None,
    )


def _captions(name: str, times: range, media_text: tuple[str, ...] = ()) -> tuple[Caption, ...]:
    video = probe(FIXTURES / name).video
    assert video is not None
    return tuple(
        Caption(float(t), f"fake caption {video.w}x{video.h}", 1.0, media_text) for t in times
    )


@dataclass(frozen=True)
class Golden:
    name: str
    s: AssetRecord
    bt: AssetRecord
    s1: str
    search: Callable[[str], list[dict[str, Any]]]


@pytest.fixture(
    scope="module",
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("onnx", id="onnx", marks=pytest.mark.model),
    ],
)
def golden(
    request: pytest.FixtureRequest, manifest: Any, tmp_path_factory: pytest.TempPathFactory
) -> Golden:
    name: str = request.param
    embedder: Embedder
    if name == "fake":
        embedder = FakeEmbedder()
    else:
        from tapesift.vision.embed import OnnxEmbedder

        embedder = OnnxEmbedder(Config())

    transcript = next(e for e in manifest["fixtures"] if e["name"] == "speech.mp4")["transcript"]
    s1, s2 = re.split(r"(?<=\.) ", transcript)
    s = AssetRecord(
        probe(FIXTURES / "speech.mp4"),
        (Utterance(0.0, 2.82, s1, "en", 1.0, ()), Utterance(3.2, 6.6, s2, "en", 1.0, ())),
        _captions("speech.mp4", range(7)),
        (),
        _prov(True, True),
    )
    bt = AssetRecord(
        probe(FIXTURES / "burned_text.mp4"),
        (),
        _captions("burned_text.mp4", range(3), (BURNED_TEXT,)),
        (),
        _prov(False, True),
    )
    c = AssetRecord(
        probe(FIXTURES / "clean.mp4"),
        (),
        _captions("clean.mp4", range(5)),
        (),
        _prov(False, True),
    )
    out: Path = tmp_path_factory.mktemp(f"golden-{name}")
    store = LanceStore(Config(out_dir=out), embedder)
    for rec in (s, bt, c):
        store.upsert(rec)

    def search(query: str) -> list[dict[str, Any]]:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(lance, "load_embedder", lambda: embedder)
            result = CliRunner().invoke(app, ["search", query, "--out", str(out), "--json"])
        assert result.exit_code == ExitCode.OK, result.stderr
        return json.loads(result.stdout)["hits"]

    return Golden(name, s, bt, s1, search)


def test_golden_spoken_text_rank_one(golden: Golden) -> None:
    top = golden.search("quarterly pricing review")[0]
    assert top["asset_id"] == golden.s.asset.id
    assert top["modality"] == "speech"
    assert top["start_s"] == 0.0
    assert top["end_s"] == 2.82
    assert top["text"] == golden.s1
    if golden.name == "fake":
        assert top["score"] == pytest.approx(0.654654, abs=1e-5)


def test_golden_burned_text_rank_one(golden: Golden) -> None:
    hits = golden.search("ignore previous instructions")
    assert hits[0]["asset_id"] == golden.bt.asset.id
    assert hits[0]["modality"] == "visual"
    assert hits[0]["media_text"] == [BURNED_TEXT]
    assert hits[0]["trust"] == "untrusted_media"
    if golden.name == "fake":
        assert [(h["asset_id"], h["start_s"]) for h in hits[:3]] == [
            (golden.bt.asset.id, 0.0),
            (golden.bt.asset.id, 1.0),
            (golden.bt.asset.id, 2.0),
        ]
