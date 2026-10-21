"""E5 (docs/specs/28-schema.md): AssetRecord to schema 1.0 JSON, the JSON Schema file, write_json.
Hand-built records only; no media, no models (ADR 0008). Lean subset of the spec's table."""

import copy
import dataclasses
import hashlib
import inspect
import json
import logging
import math
import os
import stat
from collections.abc import Callable, Iterator
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from tapesift.media.types import AssetInfo, AudioStreamInfo, VideoInfo
from tapesift.schema.output import SCHEMA_VERSION, to_json, write_json
from tapesift.schema.records import (
    BACKEND_ID_RE,
    AssetRecord,
    Caption,
    Provenance,
    Utterance,
    Word,
)
from tapesift.warning_codes import AssetWarning, WarningCode

W = WarningCode
A = AudioStreamInfo
Z = "0" * 40
SCHEMA_SHA256 = "ef4b01c49ef058548425138a99d8233b23bdcae9b90328d399fc6b6e9be39336"

_SCHEMA_FILE = files("tapesift.schema").joinpath("asset-1.0.schema.json")
SCHEMA: dict[str, Any] = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
V = Draft202012Validator(SCHEMA)

_T2 = 2.0333333333333332
_NO_PROV = Provenance("0.1.0.dev0", None, None, None)
_PROV = Provenance("0.1.0.dev0", "fake:asr@" + Z, "fake:vlm@" + Z, "caption_v1")


def _mk(
    asset: AssetInfo,
    utterances: tuple[Utterance, ...] = (),
    captions: tuple[Caption, ...] = (),
    warnings: tuple[AssetWarning, ...] = (),
    provenance: Provenance = _NO_PROV,
) -> AssetRecord:
    return AssetRecord(asset, utterances, captions, warnings, provenance)


FULL = _mk(
    AssetInfo(
        "tsid1:" + "ab" * 32,
        Path("dossier é/réunion 01.mp4"),
        5.933333333333334,
        VideoInfo(0, "h264", 320, 240, 1500 / 89, True, 90),
        (A(1, "aac", "und", False), A(2, "opus", "eng", True)),
        (AssetWarning(W.VFR_DETECTED, "v"),),
    ),
    (
        Utterance(
            0.5, _T2, "hello there", "en", 0.91, (Word("hello", 0.5, 1.0), Word("there", 1.0, _T2))
        ),
    ),
    (Caption(1.0, "a slide", 0.74, ("BUY NOW",)), Caption(_T2, "a chart", None, ())),
    (AssetWarning(W.MULTI_AUDIO, "2 audio streams; default is stream 2"),),
    _PROV,
)
MINIMAL = _mk(
    AssetInfo(
        "sha256:" + "0" * 64,
        Path("x.mp4"),
        None,
        VideoInfo(0, "h264", 64, 36, 1.0, False, 0),
        (),
        (),
    )
)
AUDIO_ONLY = _mk(
    AssetInfo("tsid1:" + "1" * 64, Path("music.m4a"), 6.0, None, (A(0, "aac", None, True),), ()),
    provenance=Provenance("0.1.0.dev0", "fake:asr@" + Z, None, None),
)
UNKNOWN_VIDEO = _mk(
    AssetInfo(
        "tsid1:" + "2" * 64,
        Path("u.mov"),
        1.0,
        VideoInfo(0, "unknown", None, None, None, False, 0),
        (),
        (
            AssetWarning(W.UNSUPPORTED_CODEC, "stream 0 codec unknown: no decoder"),
            AssetWarning(W.NO_AUDIO, "no audio stream; ASR skipped"),
        ),
    )
)


def _leaves(x: object) -> Iterator[object]:
    """Every value reached from x, containers included."""
    yield x
    if isinstance(x, dict):
        for v in cast("dict[str, object]", x).values():
            yield from _leaves(v)
    elif isinstance(x, list):
        for v in cast("list[object]", x):
            yield from _leaves(v)


def _desc(*path: str) -> str:
    """The description at SCHEMA['properties'][a]['properties'][b]...; 'items' steps allowed."""
    node: Any = SCHEMA
    for step in path:
        node = node["items"] if step == "items" else node["properties"][step]
    return cast("str", node["description"])


def test_schema_is_draft_2020_12() -> None:
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(SCHEMA)


def test_schema_objects_are_closed() -> None:
    seen = 0

    def visit(node: Any) -> None:
        nonlocal seen
        if not isinstance(node, dict):
            return
        n = cast("dict[str, Any]", node)
        if "properties" in n:
            seen += 1
            assert n["additionalProperties"] is False
            assert n["required"] == list(n["properties"])
            for child in n["properties"].values():
                visit(child)
        if "items" in n:
            visit(n["items"])

    visit(SCHEMA)
    assert seen >= 10


@pytest.mark.parametrize(
    "record",
    [FULL, MINIMAL, AUDIO_ONLY, UNKNOWN_VIDEO],
    ids=["FULL", "MINIMAL", "AUDIO_ONLY", "UNKNOWN_VIDEO"],
)
def test_record_validates(record: AssetRecord) -> None:
    V.validate(to_json(record))


def test_full_record_maps_exactly() -> None:
    assert to_json(FULL) == {
        "schema_version": "1.0",
        "asset": {
            "id": "tsid1:" + "ab" * 32,
            "path": "dossier é/réunion 01.mp4",
            "duration_s": 5.933333333333334,
            "video": {
                "codec": "h264",
                "w": 320,
                "h": 240,
                "fps_avg": 1500 / 89,
                "vfr": True,
                "rotation": 90,
            },
            "audio": {"codec": "opus", "tracks": 2, "lang": "eng"},
            "license": None,
        },
        "shots": [],
        "utterances": [
            {
                "start_s": 0.5,
                "end_s": 2.0333333333333332,
                "text": "hello there",
                "lang": "en",
                "conf": 0.91,
                "words": [
                    {"w": "hello", "start_s": 0.5, "end_s": 1.0},
                    {"w": "there", "start_s": 1.0, "end_s": 2.0333333333333332},
                ],
            }
        ],
        "captions": [
            {"t_s": 1.0, "shot": None, "text": "a slide", "conf": 0.74, "media_text": ["BUY NOW"]},
            {
                "t_s": 2.0333333333333332,
                "shot": None,
                "text": "a chart",
                "conf": None,
                "media_text": [],
            },
        ],
        "warnings": [
            {"code": "MULTI_AUDIO", "detail": "2 audio streams; default is stream 2"},
            {"code": "VFR_DETECTED", "detail": "v"},
        ],
        "provenance": {
            "tapesift": "0.1.0.dev0",
            "asr": "fake:asr@" + Z,
            "vlm": "fake:vlm@" + Z,
            "prompt": "caption_v1",
        },
    }


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        pytest.param(
            SCHEMA["properties"]["schema_version"]["const"], SCHEMA_VERSION, id="schema_version"
        ),
        pytest.param(
            SCHEMA["properties"]["asset"]["properties"]["id"]["pattern"],
            r"^(tsid1|sha256):[0-9a-f]{64}(?!\n)$",
            id="asset_id",
        ),
        pytest.param(
            SCHEMA["properties"]["provenance"]["properties"]["asr"]["pattern"],
            "^" + BACKEND_ID_RE.pattern + r"(?!\n)$",
            id="asr",
        ),
        pytest.param(
            SCHEMA["properties"]["provenance"]["properties"]["vlm"]["pattern"],
            "^" + BACKEND_ID_RE.pattern + r"(?!\n)$",
            id="vlm",
        ),
        pytest.param(
            SCHEMA["properties"]["warnings"]["items"]["properties"]["code"]["enum"],
            [c.value for c in WarningCode],
            id="warning_codes",
        ),
    ],
)
def test_schema_agrees_with_code(actual: object, expected: object) -> None:
    assert actual == expected


def _set(path: tuple[str | int, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(d: dict[str, Any]) -> None:
        node: Any = d
        for step in path[:-1]:
            node = node[step]
        node[path[-1]] = value

    return mutate


def _add_top_key(d: dict[str, Any]) -> None:
    d["extra"] = 1


_INVALID: dict[str, Callable[[dict[str, Any]], None]] = {
    "extra_top_level_key": _add_top_key,
    "internal_index_leaks": _set(("asset", "video", "index"), 0),
    "id_trailing_newline": _set(("asset", "id"), "tsid1:" + "ab" * 32 + "\n"),
    "asr_trailing_newline": _set(("provenance", "asr"), "fake:asr@" + Z + "\n"),
    "unknown_code": _set(("warnings", 0, "code"), "STAGE_FAILED"),
    "conf_above_1": _set(("utterances", 0, "conf"), 1.5),
}


@pytest.mark.parametrize("case", list(_INVALID))
def test_invalid_output_rejected(case: str) -> None:
    d = copy.deepcopy(to_json(FULL))
    _INVALID[case](d)
    assert V.is_valid(cast("Any", d)) is False


def test_descriptions_document_semantics() -> None:
    for path in (
        ("utterances", "items", "text"),
        ("captions", "items", "text"),
        ("captions", "items", "media_text"),
    ):
        d = _desc(*path)
        assert "Untrusted" in d, path
        assert "prompt injection" in d, path
    assert "privacy" in _desc("asset", "path")


def test_write_json_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    write_json(FULL, p)
    assert json.loads(p.read_text(encoding="utf-8")) == to_json(FULL)


def test_write_json_bytes_are_stable(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    write_json(FULL, a)
    write_json(FULL, b)
    data = a.read_bytes()
    assert data == b.read_bytes()
    assert data.startswith(b'{\n  "schema_version": "1.0",\n  "asset": {\n')
    assert data.endswith(b"}\n")
    assert "réunion".encode() in data


def test_write_json_replaces_existing(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    p.write_bytes(b"old")
    write_json(FULL, p)
    assert json.loads(p.read_text(encoding="utf-8")) == to_json(FULL)
    assert sorted(x.name for x in tmp_path.iterdir()) == ["a.json"]


def test_write_json_failure_keeps_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "a.json"
    p.write_bytes(b"old")

    def boom(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("tapesift.schema.output._sync", boom)
    with pytest.raises(OSError, match="disk full"):
        write_json(FULL, p)
    assert p.read_bytes() == b"old"
    assert sorted(x.name for x in tmp_path.iterdir()) == ["a.json"]


def test_write_json_rejects_nan(tmp_path: Path) -> None:
    video = cast("VideoInfo", MINIMAL.asset.video)
    bad = dataclasses.replace(
        MINIMAL,
        asset=dataclasses.replace(
            MINIMAL.asset, video=dataclasses.replace(video, fps_avg=math.nan)
        ),
    )
    with pytest.raises(ValueError, match="JSON"):
        write_json(bad, tmp_path / "a.json")
    assert list(tmp_path.iterdir()) == []


def test_write_json_syncs_file_then_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tapesift.schema import output

    real = output._sync  # pyright: ignore[reportPrivateUsage]
    seen: list[bool] = []

    def spy(fd: int) -> None:
        seen.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real(fd)

    monkeypatch.setattr("tapesift.schema.output._sync", spy)
    write_json(FULL, tmp_path / "a.json")
    assert seen == [False, True]


def test_write_json_folder_sync_failure_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from tapesift.schema import output

    real = output._sync  # pyright: ignore[reportPrivateUsage]

    def flaky(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(22, "Invalid argument")
        real(fd)

    monkeypatch.setattr("tapesift.schema.output._sync", flaky)
    p = tmp_path / "a.json"
    with caplog.at_level(logging.WARNING):
        write_json(FULL, p)
    assert json.loads(p.read_text(encoding="utf-8")) == to_json(FULL)
    warns = [r for r in caplog.records if r.name == "tapesift.schema.output"]
    assert len(warns) == 1
    assert warns[0].levelno == logging.WARNING
    assert warns[0].getMessage().startswith("wrote a.json but could not sync its folder")


def test_write_json_replaces_symlink(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_bytes(b"keep")
    link = tmp_path / "link.json"
    link.symlink_to(elsewhere)
    write_json(FULL, link)
    assert not link.is_symlink()
    assert json.loads(link.read_text(encoding="utf-8")) == to_json(FULL)
    assert elsewhere.read_bytes() == b"keep"


def test_write_json_does_not_follow_planted_temp_symlink(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"keep")
    (tmp_path / f".tapesift-{os.getpid()}.tmp").symlink_to(victim)
    write_json(FULL, tmp_path / "a.json")
    assert victim.read_bytes() == b"keep"
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == to_json(FULL)
    assert sorted(x.name for x in tmp_path.iterdir()) == ["a.json", "victim.txt"]


def test_schema_file_is_pinned() -> None:
    assert hashlib.sha256(_SCHEMA_FILE.read_bytes()).hexdigest() == SCHEMA_SHA256


def test_numpy_scalars_become_floats() -> None:
    f32, f64 = np.float32, np.float64
    r = _mk(
        MINIMAL.asset,
        (
            Utterance(
                cast("float", f32(0.5)),
                cast("float", f32(2.82)),
                "t",
                "en",
                cast("float", f32(0.9)),
                (Word("t", cast("float", f64(0.5)), cast("float", f64(1.5))),),
            ),
        ),
        (Caption(cast("float", f32(1.0)), "c", cast("float", f32(0.5)), ()),),
        provenance=_PROV,
    )
    out = to_json(r)
    u = cast("list[Any]", out["utterances"])[0]
    assert u["end_s"] == float(f32(2.82)) == 2.819999933242798
    for x in _leaves(out):
        if isinstance(x, float):
            assert type(x) is float
    json.dumps(out)
    V.validate(out)


def test_negative_zero_written_as_zero(tmp_path: Path) -> None:
    r = _mk(
        MINIMAL.asset,
        (Utterance(-0.0, 1.0, "a", "en", 0.5, (Word("a", -0.0, 1.0),)),),
        (Caption(-0.0, "c", None, ()),),
        provenance=_PROV,
    )
    out = to_json(r)
    u = cast("list[Any]", out["utterances"])[0]
    c = cast("list[Any]", out["captions"])[0]
    for x in (u["start_s"], u["words"][0]["start_s"], c["t_s"]):
        assert x == 0.0
        assert math.copysign(1.0, x) == 1.0
    write_json(r, tmp_path / "a.json")
    assert b"-0.0" not in (tmp_path / "a.json").read_bytes()


def test_mapper_stays_small() -> None:
    assert len(inspect.getsource(to_json).splitlines()) <= 50


def test_output_is_plain_json_types() -> None:
    out = to_json(FULL)
    allowed = {dict, list, str, int, float, bool, type(None)}
    for x in _leaves(out):
        assert type(x) in allowed, x
    asset = cast("dict[str, Any]", out["asset"])
    for x in (
        asset["video"]["w"],
        asset["video"]["h"],
        asset["video"]["rotation"],
        asset["audio"]["tracks"],
    ):
        assert type(x) is int
