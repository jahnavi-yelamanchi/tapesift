"""`tapesift search` (docs/specs/29-search.md, E6 CLI tests). LanceStore with FakeEmbedder; the
model loader is patched, so no weights load (ADR 0008)."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.fakes import FakeEmbedder
from typer.testing import CliRunner

import tapesift
from tapesift.cli import ExitCode, app
from tapesift.cli.search import render
from tapesift.config import Config, ModelLoadError
from tapesift.media.types import AssetInfo
from tapesift.schema.records import AssetRecord, Caption, Hit, Modality, Provenance, Utterance
from tapesift.store import lance
from tapesift.store.lance import LanceStore

Z = "0" * 40
A_ID = "tsid1:" + "a" * 64
B_ID = "tsid1:" + "b" * 64
C_ID = "tsid1:" + "c" * 64
QUERY = "quarterly pricing review"
HIT_KEYS = [
    "asset_id",
    "path",
    "start_s",
    "end_s",
    "modality",
    "text",
    "media_text",
    "score",
    "trust",
]

runner = CliRunner()


class OtherEmbedder(FakeEmbedder):
    id = "fake:other@" + Z


def prov(asr: bool, vlm: bool) -> Provenance:
    return Provenance(
        tapesift.__version__,
        "fake:asr@" + Z if asr else None,
        "fake:vlm@" + Z if vlm else None,
        "caption_v1" if vlm else None,
    )


def record(
    asset_id: str,
    path: str,
    duration: float,
    utterances: tuple[Utterance, ...] = (),
    captions: tuple[Caption, ...] = (),
) -> AssetRecord:
    asset = AssetInfo(asset_id, Path(path), duration, None, (), ())
    return AssetRecord(asset, utterances, captions, (), prov(bool(utterances), bool(captions)))


A = record(
    A_ID,
    "/media/talk.mp4",
    10.0,
    utterances=(
        Utterance(1.5, 4.25, "The quarterly pricing review starts at nine.", "en", 1.0, ()),
        Utterance(5.0, 8.0, "Revenue grew twelve percent while costs stayed flat.", "en", 1.0, ()),
    ),
)
B = record(
    B_ID,
    "/media/slides.mp4",
    100.0,
    captions=(Caption(62.0, "a slide", 1.0, ("BUY NOW",)), Caption(63.0, "a chart", None, ())),
)


def seed(out: Path, *records: AssetRecord) -> Path:
    store = LanceStore(Config(out_dir=out), FakeEmbedder())
    for r in records:
        store.upsert(r)
    return out


@pytest.fixture(autouse=True)
def fake_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lance, "load_embedder", FakeEmbedder)


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return seed(tmp_path / "out", A, B)


def run(*args: str | Path) -> Any:
    return runner.invoke(app, ["search", *map(str, args)])


def test_json_shape_exact(out: Path) -> None:
    result = run(QUERY, "--out", out, "--k", "2", "--json")
    assert result.exit_code == ExitCode.OK
    data = json.loads(result.stdout)
    assert list(data) == ["query", "hits"]
    assert data["query"] == QUERY
    assert len(data["hits"]) == 2
    for hit in data["hits"]:
        assert list(hit) == HIT_KEYS
    first = data["hits"][0]
    assert first["asset_id"] == A_ID
    assert first["path"] == "/media/talk.mp4"
    assert first["modality"] == "speech"
    assert (first["start_s"], first["end_s"]) == (1.5, 4.25)
    assert first["media_text"] == []
    assert first["trust"] == "untrusted_media"


def test_human_output_exact(out: Path) -> None:
    result = run(QUERY, "--out", out, "--k", "4")
    assert result.exit_code == ExitCode.OK
    a, b = "a" * 64, "b" * 64
    assert result.stdout == (
        f'4 results for "{QUERY}" (text from media; untrusted)\n'
        f'1  0.655  speech  0:00:01.50-0:00:04.25  "/media/talk.mp4"  "tsid1:{a}"\n'
        '   text: "The quarterly pricing review starts at nine."\n'
        f'2  0.000  speech  0:00:05.00-0:00:08.00  "/media/talk.mp4"  "tsid1:{a}"\n'
        '   text: "Revenue grew twelve percent while costs stayed flat."\n'
        f'3  0.000  visual  0:01:02.00  "/media/slides.mp4"  "tsid1:{b}"\n'
        '   text: "a slide"\n'
        '   on-screen: "BUY NOW"\n'
        f'4  0.000  visual  0:01:03.00  "/media/slides.mp4"  "tsid1:{b}"\n'
        '   text: "a chart"\n'
    )


def test_human_output_escapes_untrusted_text(tmp_path: Path) -> None:
    hostile = "\x1b[31mRED‮\nNEXT"
    rec = record(
        B_ID, "/media/slides.mp4", 100.0, captions=(Caption(5.0, "sign", 1.0, (hostile,)),)
    )
    out = seed(tmp_path / "out", rec)
    result = run("sign", "--out", out)
    assert result.exit_code == ExitCode.OK
    assert "\x1b" not in result.stdout
    assert "‮" not in result.stdout
    assert len(result.stdout.splitlines()) == 4  # header, hit, text, on-screen: no extra line
    assert 'on-screen: "\\u001b[31mRED\\u202e\\u000aNEXT"' in result.stdout


def test_no_index_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> FakeEmbedder:
        raise AssertionError("the model must not load")

    monkeypatch.setattr(lance, "load_embedder", boom)
    o = tmp_path / "o"
    o.mkdir()
    result = run(QUERY, "--out", o)
    assert result.exit_code == ExitCode.BAD_INPUT
    assert result.stderr == f'error: no index at {o}: run "tapesift index" first, or pass --out\n'
    assert not (o / "store").exists()


def test_model_load_error_exits_3(out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> FakeEmbedder:
        raise ModelLoadError("fake: no model")

    monkeypatch.setattr(lance, "load_embedder", fail)
    result = run(QUERY, "--out", out)
    assert result.exit_code == ExitCode.ENVIRONMENT
    assert result.stderr == "error: fake: no model\n"


def test_error_messages_are_escaped(out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> FakeEmbedder:
        raise ModelLoadError("bad\x1b[31m\nnext")

    monkeypatch.setattr(lance, "load_embedder", fail)
    result = run(QUERY, "--out", out)
    assert result.stderr == "error: bad\\u001b[31m\\u000anext\n"


def test_non_finite_time_prints_question_mark() -> None:
    hit = Hit(A_ID, "/m.mp4", float("nan"), float("inf"), Modality.SPEECH, "t", (), 0.5)
    assert "  ?-?  " in render("q", [hit])


def test_incompatible_index_exits_2(out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lance, "load_embedder", OtherEmbedder)
    result = run(QUERY, "--out", out)
    assert result.exit_code == ExitCode.BAD_INPUT
    assert result.stderr == (
        f"error: {out / 'store'}: indexed with fake:embedder@{Z}, but this tapesift embeds with "
        f"fake:other@{Z}; index into a new --out\n"
    )


def test_config_and_out_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "t.toml").write_text('out_dir = "idx"\n', encoding="utf-8")
    seed(conf / "idx", A, B)
    other_rec = record(
        C_ID,
        "/media/other.mp4",
        10.0,
        utterances=(Utterance(0.0, 1.0, "quarterly pricing review", "en", 1.0, ()),),
    )
    other = seed(tmp_path / "other", other_rec)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    via_config = run(QUERY, "--config", conf / "t.toml", "--json")
    assert via_config.exit_code == ExitCode.OK
    assert json.loads(via_config.stdout)["hits"][0]["asset_id"] == A_ID

    via_flag = run(QUERY, "--config", conf / "t.toml", "--out", other, "--json")
    assert via_flag.exit_code == ExitCode.OK
    hits = json.loads(via_flag.stdout)["hits"]
    assert {h["asset_id"] for h in hits} == {C_ID}


def test_bad_arguments_exit_2(out: Path) -> None:
    assert run("   ", "--out", out).exit_code == ExitCode.BAD_INPUT
    bad_asset = run(QUERY, "--out", out, "--asset", "nope")
    assert bad_asset.exit_code == ExitCode.BAD_INPUT
    assert "--asset" in bad_asset.stderr
    assert run(QUERY, "--out", out, "--k", "0").exit_code == ExitCode.BAD_INPUT
    assert run(QUERY, "--out", out, "--modality", "audio").exit_code == ExitCode.BAD_INPUT
    unknown = run(QUERY, "--out", out, "--asset", C_ID, "--json")
    assert unknown.exit_code == ExitCode.OK
    assert json.loads(unknown.stdout) == {"query": QUERY, "hits": []}


def test_modality_filter(out: Path) -> None:
    result = run(QUERY, "--out", out, "--modality", "visual", "--k", "100", "--json")
    assert result.exit_code == ExitCode.OK
    hits = json.loads(result.stdout)["hits"]
    assert hits
    assert all(h["modality"] == "visual" for h in hits)


def test_search_import_is_light() -> None:
    heavy = (
        "torch",
        "transformers",
        "ctranslate2",
        "faster_whisper",
        "lancedb",
        "pyarrow",
        "onnxruntime",
        "tokenizers",
        "huggingface_hub",
        "av",
    )
    code = f"import sys, tapesift.cli.search; print(sorted({set(heavy)!r} & set(sys.modules)))"
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert done.stdout.strip() == "[]"
