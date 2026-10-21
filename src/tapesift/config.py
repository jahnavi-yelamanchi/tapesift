"""Configuration (spec, CLI and config): these pydantic models are the only home of defaults.
Also the model pins (owner Q3, 2026-10-19), Profile (moved from cli/doctor.py), the vision-extra
check and the two errors the CLI maps to exit codes. Imports pydantic and the stdlib only."""

from __future__ import annotations

import importlib.util
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_FILENAME: Final = "tapesift.toml"


class Profile(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    SERVER = "server"


class ConfigError(ValueError):
    """Bad config file or value. The message names every bad key; the CLI exits 2."""


class ModelLoadError(RuntimeError):
    """A real backend cannot load its pinned model: not cached while offline, download failed,
    or the vision extra missing. Raised by fetch_pin and backend constructors; the CLI exits 3."""


def vision_available() -> bool:
    """True when the vision extra's runtime is importable (transformers and torch)."""
    return all(importlib.util.find_spec(m) is not None for m in ("transformers", "torch"))


@dataclass(frozen=True, slots=True)
class ModelPin:
    backend: str  # "faster-whisper", "transformers" or "onnx"
    name: str  # the config value, e.g. "small"
    repo: str  # Hugging Face repo id
    revision: str  # full 40-hex commit SHA, from the HF API on 2026-10-19
    files: tuple[str, ...]  # the only files fetch_pin fetches; never a pickle (R4)

    @property
    def id(self) -> str:
        """The backend id for provenance: "<backend>:<name>@<revision>"."""
        return f"{self.backend}:{self.name}@{self.revision}"


_WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")  # CTranslate2
ASR_MODELS: Final[dict[str, ModelPin]] = {
    "small": ModelPin("faster-whisper", "small", "Systran/faster-whisper-small",
                      "536b0662742c02347bc0e980a01041f333bce120", _WHISPER_FILES),
    "tiny": ModelPin("faster-whisper", "tiny", "Systran/faster-whisper-tiny",
                     "d90ca5fe260221311c53c58e660288d3deb8d356", _WHISPER_FILES),
}  # fmt: skip
VLM_MODELS: Final[dict[str, ModelPin]] = {
    "smolvlm2-256m": ModelPin(
        "transformers", "smolvlm2-256m", "HuggingFaceTB/SmolVLM2-256M-Video-Instruct",
        "067788b187b95ebe7b2e040b3e4299e342e5b8fd",
        ("added_tokens.json", "chat_template.json", "config.json", "generation_config.json",
         "merges.txt", "model.safetensors", "preprocessor_config.json", "processor_config.json",
         "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.json"),
    ),
}  # fmt: skip
EMBEDDER: Final = ModelPin("onnx", "bge-small-en-v1.5", "BAAI/bge-small-en-v1.5",
                           "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
                           ("onnx/model.onnx", "tokenizer.json"))  # fmt: skip


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SamplingConfig(_Section):
    strategy: Literal["fixed"] = "fixed"  # "shots+dedupe" arrives with C3 (v0.2)
    fixed_fps: float = Field(default=1.0, gt=0)


class AsrConfig(_Section):
    backend: Literal["faster-whisper"] = "faster-whisper"
    model: Literal["small", "tiny"] = "small"  # keys of ASR_MODELS
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    vad_min_speech_ratio: float = Field(default=0.05, ge=0.0, le=1.0)  # below: skip ASR
    batch_seconds: float = Field(default=600.0, gt=0)  # Decoder.iter_audio chunk_s
    audio_track: int | None = Field(default=None, ge=0)  # index into AssetInfo.audio


class VlmConfig(_Section):
    backend: Literal["auto", "transformers", "none"] = "auto"  # "openai" arrives with C6
    model: Literal["smolvlm2-256m"] = "smolvlm2-256m"  # keys of VLM_MODELS
    max_batch: int | None = Field(default=None, ge=1)  # None: VLM_MAX_BATCH[profile] (card 4)
    prompt: Literal["caption_v1"] = "caption_v1"


class StoreConfig(_Section):
    backend: Literal["lancedb"] = "lancedb"


class Config(_Section):
    profile: Profile | None = None  # None: E7 fills it from doctor's pick_profile
    out_dir: Path = Path("tapesift_index")  # relative to the current directory
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    vlm: VlmConfig = Field(default_factory=VlmConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)


VLM_MAX_BATCH: Final[dict[Profile, int]] = {Profile.CPU: 8, Profile.GPU: 8, Profile.SERVER: 8}
"""Per-profile default for vlm.max_batch in v0.1; C6 raises gpu and server (card 4)."""

_PATH_KEYS: Final = (("out_dir",),)
"""Every Path-typed key, as a key path into the file's table. A relative value written in a
config file resolves against that file's folder (card 4). A test keeps this list complete."""


def vlm_max_batch(cfg: Config) -> int:
    """cfg.vlm.max_batch if set, else VLM_MAX_BATCH[cfg.profile], with None treated as cpu."""
    if cfg.vlm.max_batch is not None:
        return cfg.vlm.max_batch
    return VLM_MAX_BATCH[cfg.profile or Profile.CPU]


def load_config(
    path: Path | None = None, *, profile: Profile | None = None, out_dir: Path | None = None
) -> Config:
    """Defaults < file < flags. path is --config; None means ./tapesift.toml if it is a file,
    else no file. A flag that is not None overrides the file. Raises ConfigError (R7)."""
    if path is None and Path(CONFIG_FILENAME).is_file():
        path = Path(CONFIG_FILENAME)
    data: dict[str, Any] = {}
    if path is not None:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"{path}: file not found") from None
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(f"{path}: {e}") from None
        for keys in _PATH_KEYS:
            table: dict[str, Any] = data
            for key in keys[:-1]:
                sub = table.get(key)
                if not isinstance(sub, dict):
                    break
                table = cast("dict[str, Any]", sub)
            else:
                value = table.get(keys[-1])
                if isinstance(value, str) and not Path(value).is_absolute():
                    table[keys[-1]] = str(path.parent / value)
    if profile is not None:
        data["profile"] = profile
    if out_dir is not None:
        data["out_dir"] = out_dir
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        prefix = f"{path}: " if path is not None else ""
        detail = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise ConfigError(prefix + detail) from None
