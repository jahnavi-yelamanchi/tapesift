"""Issue #27: TransformersVLM's load errors and expand_image_tokens, with config.vision_available,
hub.fetch_pin and _load_parts patched (docs/specs/27-captions.md, Acceptance 14-16). Never loads
torch, transformers or weights (ADR 0008)."""

from pathlib import Path
from typing import Any

import pytest

from tapesift.config import VLM_MODELS, Config, ModelLoadError, ModelPin

# Each block below is its own isort section: the new module does not exist yet, and ruff groups a
# missing module as third-party until it does. This order is valid before and after.
# isort: split
from tapesift.vision.transformers_vlm import TransformersVLM, expand_image_tokens

_MOD = "tapesift.vision.transformers_vlm"


def test_missing_extra_is_model_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[ModelPin] = []

    def fetch_pin(pin: ModelPin, *args: Any, **kwargs: Any) -> Path:
        fetched.append(pin)
        raise AssertionError("fetch_pin must not be called without the vision extra")

    monkeypatch.setattr(f"{_MOD}.config.vision_available", lambda: False)
    monkeypatch.setattr(f"{_MOD}.hub.fetch_pin", fetch_pin)
    with pytest.raises(ModelLoadError, match=r"tapesift\[vision\]"):
        TransformersVLM(Config())
    assert fetched == []


def test_load_failure_is_model_load_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def load_parts(d: Path, device: str) -> tuple[Any, Any, Any]:
        raise OSError("bad")

    monkeypatch.setattr(f"{_MOD}.config.vision_available", lambda: True)
    monkeypatch.setattr(f"{_MOD}.hub.fetch_pin", lambda pin, *a, **k: tmp_path)
    monkeypatch.setattr(f"{_MOD}._load_parts", load_parts)
    pin = VLM_MODELS["smolvlm2-256m"]
    with pytest.raises(ModelLoadError) as exc:
        TransformersVLM(Config())
    assert str(exc.value) == (f"cannot load {pin.repo}@{pin.revision[:12]}: OSError: bad")
    assert str(exc.value) == (
        "cannot load HuggingFaceTB/SmolVLM2-256M-Video-Instruct@067788b187b9: OSError: bad"
    )


def test_expand_image_tokens() -> None:
    assert expand_image_tokens("U:<image>hi", "<x><y>") == "U:<x><y>hi"
    with pytest.raises(ValueError):
        expand_image_tokens("U:hi", "<x>")
    with pytest.raises(ValueError):
        expand_image_tokens("<image>U:<image>", "<x>")
