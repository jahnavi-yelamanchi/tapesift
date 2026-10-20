"""Config models, pins and load_config (spec 25, cards 4 and 6, R3, R4, R7)."""

import importlib.machinery
import importlib.util
import re
import typing
from pathlib import Path

import pytest
import tapesift.config
from pydantic import BaseModel, ValidationError
from tapesift.config import (
    _PATH_KEYS,  # pyright: ignore[reportPrivateUsage]
    ASR_MODELS,
    EMBEDDER,
    VLM_MAX_BATCH,
    VLM_MODELS,
    AsrConfig,
    Config,
    ConfigError,
    ModelPin,
    Profile,
    VlmConfig,
    load_config,
    vision_available,
    vlm_max_batch,
)
from tapesift.schema.records import BACKEND_ID_RE

from tapesift.cli.doctor import Profile as DoctorProfile


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---- defaults and discovery -----------------------------------------------


def test_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config().model_dump(mode="json") == {
        "profile": None,
        "out_dir": "tapesift_index",
        "sampling": {"strategy": "fixed", "fixed_fps": 1.0},
        "asr": {
            "backend": "faster-whisper",
            "model": "small",
            "compute_type": "int8",
            "vad_min_speech_ratio": 0.05,
            "batch_seconds": 600.0,
            "audio_track": None,
        },
        "vlm": {
            "backend": "auto",
            "model": "smolvlm2-256m",
            "max_batch": None,
            "prompt": "caption_v1",
        },
        "store": {"backend": "lancedb"},
    }


def test_empty_file_is_valid(tmp_path: Path) -> None:
    assert load_config(_write(tmp_path / "t.toml", "")) == Config()


def test_discovers_toml_in_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "tapesift.toml", "[vlm]\nmax_batch = 4\n")
    assert load_config().vlm.max_batch == 4


# ---- errors name the dotted key -------------------------------------------


@pytest.mark.parametrize(
    ("toml", "loc"),
    [
        pytest.param("colour = 1\n", "colour", id="top_level"),
        pytest.param('[asr]\nmodle = "x"\n', "asr.modle", id="nested"),
        pytest.param("[safety]\nredact_pii = false\n", "safety", id="unimplemented_section"),
        pytest.param(
            "[sampling]\nshot_threshold = 27.0\n", "sampling.shot_threshold", id="later_key"
        ),
    ],
)
def test_unknown_key_is_named(tmp_path: Path, toml: str, loc: str) -> None:
    p = _write(tmp_path / "t.toml", toml)
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(e.value) == f"{p}: {loc}: Extra inputs are not permitted"


@pytest.mark.parametrize(
    ("toml", "loc", "msg"),
    [
        pytest.param(
            '[asr]\nmodel = "large-v3-turbo"\n',
            "asr.model",
            "Input should be 'small' or 'tiny'",
            id="asr_model",
        ),
        pytest.param(
            '[sampling]\nstrategy = "shots+dedupe"\n',
            "sampling.strategy",
            "Input should be 'fixed'",
            id="strategy",
        ),
        pytest.param(
            "[sampling]\nfixed_fps = 0\n",
            "sampling.fixed_fps",
            "Input should be greater than 0",
            id="fps_zero",
        ),
        pytest.param(
            "[sampling]\nfixed_fps = inf\n",
            "sampling.fixed_fps",
            "Input should be a finite number",
            id="fps_inf",
        ),
        pytest.param(
            "[asr]\nvad_min_speech_ratio = 1.5\n",
            "asr.vad_min_speech_ratio",
            "Input should be less than or equal to 1",
            id="ratio_high",
        ),
        pytest.param(
            "[vlm]\nmax_batch = 0\n",
            "vlm.max_batch",
            "Input should be greater than or equal to 1",
            id="max_batch_zero",
        ),
        pytest.param(
            'profile = "tpu"\n',
            "profile",
            "Input should be 'cpu', 'gpu' or 'server'",
            id="profile",
        ),
        pytest.param(
            "[asr]\naudio_track = -1\n",
            "asr.audio_track",
            "Input should be greater than or equal to 0",
            id="audio_track_negative",
        ),
    ],
)
def test_bad_value_is_named(tmp_path: Path, toml: str, loc: str, msg: str) -> None:
    p = _write(tmp_path / "t.toml", toml)
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(e.value) == f"{p}: {loc}: {msg}"


def test_every_bad_key_is_reported(tmp_path: Path) -> None:
    p = _write(tmp_path / "t.toml", "colour = 1\n[vlm]\nmax_batch = 0\n")
    with pytest.raises(ConfigError) as e:
        load_config(p)
    message = str(e.value)
    assert "colour: Extra inputs are not permitted" in message
    assert "vlm.max_batch: Input should be greater than or equal to 1" in message
    assert "; " in message


def test_toml_syntax_error(tmp_path: Path) -> None:
    p = _write(tmp_path / "t.toml", "asr = [")
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(e.value).startswith(f"{p}: ")


def test_explicit_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "nope.toml"
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(e.value) == f"{p}: file not found"


# ---- precedence -----------------------------------------------------------


def test_flags_override_file(tmp_path: Path) -> None:
    p = _write(tmp_path / "t.toml", 'profile = "gpu"\nout_dir = "a"\n')
    flagged = load_config(p, profile=Profile.CPU, out_dir=Path("b"))
    assert flagged.profile is Profile.CPU
    assert flagged.out_dir == Path("b")
    from_file = load_config(p)
    assert from_file.profile is Profile.GPU
    assert from_file.out_dir == tmp_path / "a"


def test_config_is_frozen() -> None:
    cfg = Config()
    with pytest.raises(ValidationError):
        setattr(cfg.asr, "model", "tiny")  # noqa: B010


# ---- model pins -----------------------------------------------------------

_PICKLE_FILE = re.compile(r"(pytorch_model|\.pt$|\.pth$|\.pkl$|\.pickle$|\.ckpt$)")


@pytest.mark.parametrize(
    ("pin", "repo", "sha"),
    [
        pytest.param(
            ASR_MODELS["small"],
            "Systran/faster-whisper-small",
            "536b0662742c02347bc0e980a01041f333bce120",
            id="small",
        ),
        pytest.param(
            ASR_MODELS["tiny"],
            "Systran/faster-whisper-tiny",
            "d90ca5fe260221311c53c58e660288d3deb8d356",
            id="tiny",
        ),
        pytest.param(
            VLM_MODELS["smolvlm2-256m"],
            "HuggingFaceTB/SmolVLM2-256M-Video-Instruct",
            "067788b187b95ebe7b2e040b3e4299e342e5b8fd",
            id="smolvlm2-256m",
        ),
        pytest.param(
            EMBEDDER,
            "BAAI/bge-small-en-v1.5",
            "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
            id="bge-small-en-v1.5",
        ),
    ],
)
def test_model_pins(pin: ModelPin, repo: str, sha: str) -> None:
    assert pin.repo == repo
    assert pin.revision == sha
    assert re.fullmatch(r"[0-9a-f]{40}", pin.revision)
    assert not [f for f in pin.files if _PICKLE_FILE.search(f)]
    assert BACKEND_ID_RE.fullmatch(pin.id)


def test_config_names_match_pins() -> None:
    asr = typing.get_args(AsrConfig.model_fields["model"].annotation)
    vlm = typing.get_args(VlmConfig.model_fields["model"].annotation)
    assert asr == tuple(ASR_MODELS)
    assert vlm == tuple(VLM_MODELS)


def test_profile_moved_to_config() -> None:
    assert DoctorProfile is tapesift.config.Profile


# ---- vision extra and batch size ------------------------------------------


@pytest.mark.parametrize(
    ("missing", "expected"),
    [pytest.param(None, True, id="both_found"), pytest.param("torch", False, id="torch_missing")],
)
def test_vision_available(
    monkeypatch: pytest.MonkeyPatch, missing: str | None, expected: bool
) -> None:
    def find_spec(name: str, package: str | None = None) -> importlib.machinery.ModuleSpec | None:
        return None if name == missing else importlib.machinery.ModuleSpec(name, None)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    assert vision_available() is expected


@pytest.mark.parametrize(
    ("profile", "max_batch", "expected"),
    [
        pytest.param(None, None, 8, id="unset_profile_is_cpu"),
        pytest.param(Profile.CPU, None, 8, id="cpu"),
        pytest.param(Profile.SERVER, None, VLM_MAX_BATCH[Profile.SERVER], id="server"),
        pytest.param(Profile.CPU, 16, 16, id="explicit_wins"),
    ],
)
def test_vlm_max_batch(profile: Profile | None, max_batch: int | None, expected: int) -> None:
    cfg = Config(profile=profile, vlm=VlmConfig(max_batch=max_batch))
    assert vlm_max_batch(cfg) == expected


# ---- path keys ------------------------------------------------------------


def test_file_path_resolves_against_config_folder(tmp_path: Path) -> None:
    p = _write(tmp_path / "conf" / "t.toml", 'out_dir = "idx"\n')
    assert load_config(p).out_dir == tmp_path / "conf" / "idx"


def test_absolute_file_path_is_kept(tmp_path: Path) -> None:
    p = _write(tmp_path / "conf" / "t.toml", f'out_dir = "{tmp_path / "abs"}"\n')
    assert load_config(p).out_dir == tmp_path / "abs"


def test_flag_and_default_stay_cwd_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _write(tmp_path / "conf" / "t.toml", 'out_dir = "idx"\n')
    assert load_config(conf, out_dir=Path("o")).out_dir == Path("o")
    empty = _write(tmp_path / "conf" / "empty.toml", "")
    assert load_config(empty).out_dir == Path("tapesift_index")


def _path_key_paths(model: type[BaseModel], prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    for name, field in model.model_fields.items():
        options = typing.get_args(field.annotation) or (field.annotation,)
        if Path in options:
            found.add((*prefix, name))
        for opt in options:
            if isinstance(opt, type) and issubclass(opt, BaseModel):
                found |= _path_key_paths(opt, (*prefix, name))
    return found


def test_every_path_field_is_listed() -> None:
    assert _path_key_paths(Config) == set(_PATH_KEYS)
