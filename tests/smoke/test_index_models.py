"""`tapesift index` with the real pinned models on every fixture (docs/specs/30-runner.md,
test_index_models.py; spec 333: "CI indexes all fixtures on CPU"). Runs only in the CI `models` job,
never on the laptop (ADR 0008). No patches: the real `load` and `open_store` run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from tests.smoke.conftest import FIXTURES

from tapesift.config import ASR_MODELS, VLM_MODELS, vision_available
from tapesift.runner.run import asset_file_name

pytestmark = pytest.mark.model

INVALID = "InvalidDataError: Invalid data found when processing input"
CLEAN_COPY_DETAIL = f"same content as {FIXTURES.absolute() / 'clean.mp4'}"
SCHEMA = json.loads(
    files("tapesift.schema").joinpath("asset-1.0.schema.json").read_text(encoding="utf-8")
)

TIMEOUT_S = 1800

# A subprocess, not CliRunner: pytest's live log (-o log_cli, set by the models job) swaps
# sys.stdout when a log record arrives, which closes CliRunner's captured stream.


def tapesift(*args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"}  # no progress bar
    return subprocess.run(
        [sys.executable, "-m", "tapesift", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env=env,
    )


@pytest.fixture(scope="module")
def conf(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """(config file, out dir). 0.005 fps gives long_3h.mp4 54 frames."""
    root = tmp_path_factory.mktemp("models")
    cfg = root / "tapesift.toml"
    cfg.write_text(
        'profile = "cpu"\n\n[asr]\nmodel = "tiny"\n\n[sampling]\nfixed_fps = 0.005\n',
        encoding="utf-8",
    )
    return cfg, root / "out"


def by_name(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {Path(r["path"]).name: r for r in doc["files"]}


def _index(conf: tuple[Path, Path]) -> tuple[int, dict[str, Any]]:
    cfg, out = conf
    r = tapesift("index", str(FIXTURES), "--config", str(cfg), "--out", str(out), "--json")
    assert r.stdout, r.stderr
    return r.returncode, json.loads(r.stdout)


def _search(conf: tuple[Path, Path], query: str) -> dict[str, Any]:
    cfg, out = conf
    r = tapesift("search", query, "--config", str(cfg), "--out", str(out), "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_models_index_all_fixtures(conf: tuple[Path, Path]) -> None:
    code, doc = _index(conf)
    assert code == 1
    files_ = by_name(doc)
    assert doc["total"] == 26
    failed = {n for n, r in files_.items() if r["status"] == "failed"}
    assert failed == {"not_media.txt", "manifest.json"}
    assert all(files_[n]["detail"] == INVALID for n in failed)
    dups = {n: r for n, r in files_.items() if r["status"] == "duplicate"}
    assert {n: r["detail"] for n, r in dups.items()} == {"clean_copy.mp4": CLEAN_COPY_DETAIL}
    assert doc["counts"]["indexed"] == 23
    assert files_["truncated.mp4"]["status"] == "indexed"
    assert files_["unknown_codec.mov"]["status"] == "indexed"

    v = Draft202012Validator(SCHEMA)
    out = conf[1]
    docs = sorted((out / "assets").glob("*.json"))
    assert len(docs) == 23
    for p in docs:
        v.validate(json.loads(p.read_text(encoding="utf-8")))

    speech_json = out / "assets" / asset_file_name(files_["speech.mp4"]["asset_id"])
    speech = json.loads(speech_json.read_text(encoding="utf-8"))
    assert speech["provenance"]["asr"] == ASR_MODELS["tiny"].id
    if vision_available():
        assert speech["provenance"]["vlm"] == VLM_MODELS["smolvlm2-256m"].id


def test_models_rerun_skips(conf: tuple[Path, Path]) -> None:
    _index(conf)  # a no-op after the first test; makes this test stand alone
    code, doc = _index(conf)
    assert code == 1
    c = doc["counts"]
    assert (c["skipped"], c["duplicate"], c["failed"], c["indexed"]) == (23, 1, 2, 0)

    # The MVP demo on real models: search what the index just stored.
    assert isinstance(_search(conf, "fixture")["hits"], list)
    out = conf[1]
    utterances = [
        u["text"]
        for p in sorted((out / "assets").glob("*.json"))
        for u in json.loads(p.read_text(encoding="utf-8")).get("utterances", [])
        if u.get("text")
    ]
    assert utterances, "no stored utterance to search for"
    assert len(_search(conf, utterances[0])["hits"]) >= 1
