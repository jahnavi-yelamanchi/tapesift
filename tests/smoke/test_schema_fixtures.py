"""E5 (docs/specs/28-schema.md): real probe and PyAVDecoder, fake models (ADR 0008), every manifest
fixture mapped to schema 1.0 and validated. Snapshots check structure and timestamps, never model
text (docs/spec.md, Engineering standards)."""

import copy
import itertools
import json
import re
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import FIXTURES
from jsonschema import Draft202012Validator

# Each block is its own isort section so CI and a local checkout order it the same way
# (first-party detection differs between them).
# isort: split
import tapesift
from tapesift.media.decode import PyAVDecoder
from tapesift.media.probe import probe
from tapesift.media.types import AssetInfo, ProbeError

# isort: split
from tapesift.schema.output import to_json, write_json
from tapesift.schema.records import AssetRecord, Caption, Provenance, Utterance, clamp_utterance
from tapesift.warning_codes import AssetWarning, StageError, WarningCode

# isort: split
from tests.fakes import FakeASR, FakeVLM

W = WarningCode
SCHEMA: dict[str, Any] = json.loads(
    files("tapesift.schema").joinpath("asset-1.0.schema.json").read_text(encoding="utf-8")
)
V = Draft202012Validator(SCHEMA)

ASR, VLM, D = FakeASR(), FakeVLM(), PyAVDecoder()
MAX_FRAMES = 8  # long_3h.mp4 would give 10 800 captions; the shape is the same after 8
# Manifest codes that no probe or decode stage emits (docs/specs/5-probe.md).
_OWNED_ELSEWHERE = frozenset({W.CROPPED, W.LOW_SPEECH, W.MEDIA_TEXT, W.DUPLICATE})
_JSON_TYPES = {dict, list, str, int, float, bool, type(None)}

_ENTRIES: list[Any] = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))[
    "fixtures"
]


def _record(info: AssetInfo) -> AssetRecord:
    """Builds records the way E3, E4 and E7 would with fakes (M1 R2 and R5)."""
    sink: list[AssetWarning] = []
    utts: list[Utterance] = []
    caps: list[Caption] = []
    try:
        for chunk in D.iter_audio(info, warn=sink.append):  # 600 s chunks: one per fixture
            end = chunk.start_s + len(chunk.samples) / chunk.sample_rate
            hi = end if info.duration_s is None else min(end, info.duration_s)
            utts += [
                c
                for u in ASR.transcribe([chunk])[0]
                if (c := clamp_utterance(u, chunk.start_s, hi))
            ]
    except StageError as e:
        sink.append(e.warning)
    try:
        frames = list(itertools.islice(D.iter_frames(info, 1.0, warn=sink.append), MAX_FRAMES))
        caps = VLM.caption(frames, "caption_v1")
    except StageError as e:
        sink.append(e.warning)
    return AssetRecord(
        info,
        tuple(utts),
        tuple(caps),
        tuple(sink),
        Provenance(
            tapesift.__version__,
            ASR.id if utts else None,
            VLM.id if caps else None,
            "caption_v1" if caps else None,
        ),
    )


def _out(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", to_json(_record(probe(FIXTURES / name))))


def _leaves(x: object) -> Iterator[object]:
    yield x
    if isinstance(x, dict):
        for v in cast("dict[str, object]", x).values():
            yield from _leaves(v)
    elif isinstance(x, list):
        for v in cast("list[object]", x):
            yield from _leaves(v)


@pytest.mark.parametrize("entry", _ENTRIES, ids=[e["name"] for e in _ENTRIES])
def test_every_fixture_output_validates(entry: dict[str, Any], tmp_path: Path) -> None:
    name: str = entry["name"]
    if name == "not_media.txt":
        with pytest.raises(ProbeError) as ei:
            probe(FIXTURES / name)
        assert ei.value.warning.code == W.UNREADABLE
        return
    info = probe(FIXTURES / name)
    record = _record(info)
    out = cast("dict[str, Any]", to_json(record))
    V.validate(out)
    write_json(record, tmp_path / "out.json")
    assert json.loads((tmp_path / "out.json").read_text(encoding="utf-8")) == out
    assert out["asset"]["path"] == str(FIXTURES / name)
    expected = {c for c in entry["warning_codes"] if W(c) not in _OWNED_ELSEWHERE}
    assert expected <= {w["code"] for w in out["warnings"]}
    for x in _leaves(out):
        assert type(x) in _JSON_TYPES, x
    blanked = copy.deepcopy(out)
    blanked["asset"]["path"] = ""
    text = json.dumps(blanked, ensure_ascii=False)
    assert str(FIXTURES) not in text
    assert str(FIXTURES.resolve()) not in text


def test_clean_snapshot() -> None:
    out = _out("clean.mp4")
    assert list(out) == list(SCHEMA["properties"])
    asset = dict(out["asset"])
    assert re.fullmatch(r"(tsid1|sha256):[0-9a-f]{64}", asset.pop("id"))
    assert asset == {
        "path": str(FIXTURES / "clean.mp4"),
        "duration_s": 5.0,
        "video": {
            "codec": "h264",
            "w": 320,
            "h": 240,
            "fps_avg": 25.0,
            "vfr": False,
            "rotation": 0,
        },
        "audio": {"codec": "aac", "tracks": 1, "lang": "und"},
        "license": None,
    }
    assert out["shots"] == []
    assert out["utterances"] == []
    caps = out["captions"]
    assert len(caps) == 5
    for c, t in zip(caps, [0.0, 1.0, 2.0, 3.0, 4.0], strict=True):
        assert c["t_s"] == pytest.approx(t, abs=1e-6)
        assert (c["shot"], c["conf"], c["media_text"], type(c["text"])) == (None, 1.0, [], str)
    assert out["warnings"] == []
    assert out["provenance"] == {
        "tapesift": tapesift.__version__,
        "asr": None,
        "vlm": "fake:vlm@" + "0" * 40,
        "prompt": "caption_v1",
    }


def test_speech_snapshot() -> None:
    out = _out("speech.mp4")
    asset = out["asset"]
    assert asset["duration_s"] == 7.0
    assert asset["video"] == {
        "codec": "h264",
        "w": 320,
        "h": 180,
        "fps_avg": 5.0,
        "vfr": False,
        "rotation": 0,
    }
    utts = out["utterances"]
    assert len(utts) == 2
    for u, (s, e) in zip(utts, [(0.0, 2.82), (3.2, 6.6)], strict=True):
        assert u["start_s"] == pytest.approx(s, abs=0.02)
        assert u["end_s"] == pytest.approx(e, abs=0.02)
        assert u["lang"] == "en"
        assert u["conf"] == 1.0
        assert type(u["text"]) is str
        assert len(u["words"]) == 2
        assert u["words"][0]["start_s"] == u["start_s"]
        assert u["words"][-1]["end_s"] == u["end_s"]
    caps = out["captions"]
    assert [c["t_s"] for c in caps] == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0], abs=1e-6)
    assert out["provenance"]["asr"] == "fake:asr@" + "0" * 40
