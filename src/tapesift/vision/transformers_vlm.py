"""TransformersVLM: the pinned SmolVLM2 in-process through transformers (vision extra, ADR 0002).
Importing this module imports neither torch nor transformers (M1 R6); _load_parts and caption do.
Built from parts (card 1): the PIL image processor, the tokenizer and the model; SmolVLMProcessor
is never built. Deterministic for the same frames in the same batch on the same machine and
thread count; a different batch split or CPU may change a reply. Caption.conf is None (card 5)."""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, cast

from tapesift import config, hub
from tapesift.config import Config, ModelLoadError
from tapesift.media.types import Frame
from tapesift.schema.records import Caption
from tapesift.vision.prompts import PROMPTS, PromptSpec, is_prompt_echo, parse_reply

log = logging.getLogger(__name__)

SEED: Final = 0  # torch.manual_seed before every generate; decoding is greedy
IMAGE_TOKEN: Final = "<image>"  # noqa: S105 (a tokenizer token, not a secret)
FAKE_TOKEN: Final = "<fake_token_around_image>"  # noqa: S105
GLOBAL_TOKEN: Final = "<global-img>"  # noqa: S105


def expand_image_tokens(chat: str, image_prompt: str) -> str:
    """chat with its single IMAGE_TOKEN replaced by image_prompt. ValueError unless chat contains
    IMAGE_TOKEN exactly once."""
    if chat.count(IMAGE_TOKEN) != 1:
        raise ValueError(f"chat template must contain {IMAGE_TOKEN} exactly once")
    return chat.replace(IMAGE_TOKEN, image_prompt)


def _load_parts(d: Path, device: str) -> tuple[Any, Any, Any]:
    """(tokenizer, image_processor, model) from the snapshot dir; imports torch and transformers.
    Tests patch this; nothing else calls it."""
    torch = cast(Any, importlib.import_module("torch"))
    tf = cast(Any, importlib.import_module("transformers"))
    ip_mod = importlib.import_module("transformers.models.smolvlm.image_processing_pil_smolvlm")
    tok = tf.AutoTokenizer.from_pretrained(d, local_files_only=True, trust_remote_code=False)
    tok.padding_side = "left"
    ip = ip_mod.SmolVLMImageProcessorPil.from_pretrained(d, local_files_only=True)
    model = (
        tf.SmolVLMForConditionalGeneration.from_pretrained(
            d,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            dtype=torch.float32,
        )
        .to(device)
        .eval()
    )
    return tok, ip, model


class TransformersVLM:
    """M1's VLM."""

    def __init__(self, cfg: Config) -> None:
        if not config.vision_available():
            raise ModelLoadError('vision extra not installed: install "tapesift[vision]"')
        pin = config.VLM_MODELS[cfg.vlm.model]
        d = hub.fetch_pin(pin)
        profile = cfg.profile
        device = "cuda" if profile in (config.Profile.GPU, config.Profile.SERVER) else "cpu"
        try:
            tok, ip, model = _load_parts(d, device)
            seq = int(
                json.loads((d / "processor_config.json").read_text(encoding="utf-8"))[
                    "image_seq_len"
                ]
            )
            chat: dict[str, str] = {}
            for pid, spec in PROMPTS.items():
                text = tok.apply_chat_template(
                    [
                        {
                            "role": "user",
                            "content": [{"type": "image"}, {"type": "text", "text": spec.text}],
                        }
                    ],
                    tokenize=False,
                    add_generation_prompt=True,
                )
                if str(text).count(IMAGE_TOKEN) != 1:
                    raise ValueError(f"chat template for {pid} lacks one {IMAGE_TOKEN}")
                chat[pid] = str(text)
        except Exception as e:
            raise ModelLoadError(
                f"cannot load {pin.repo}@{pin.revision[:12]}: {type(e).__name__}: {e}"
            ) from e
        self._id = pin.id
        self._device = device
        self._tok = tok
        self._ip = ip
        self._model = model
        self._seq = seq
        self._chat = chat
        torch = cast(Any, importlib.import_module("torch"))
        log.info("TransformersVLM on %s, float32, %d threads", device, torch.get_num_threads())

    @property
    def id(self) -> str:
        return self._id

    def _prepare(self, frames: Sequence[Frame], spec: PromptSpec) -> tuple[Any, Any, list[int]]:
        """caption() steps 2-4 with their glue checks: (feats, enc, tiles per row). The models
        job (M5) and card 6's bench call it; nothing else does."""
        prompt_chat = self._chat[next(k for k, v in PROMPTS.items() if v == spec)]
        tiling: dict[str, Any] = (
            {"do_image_splitting": False}
            if spec.image_longest_edge is None
            else {"do_image_splitting": True, "size": {"longest_edge": spec.image_longest_edge}}
        )
        feats = self._ip(
            images=[[f.pixels] for f in frames],
            return_tensors="pt",
            return_row_col_info=True,
            input_data_format="channels_last",
            **tiling,
        )
        get_prompt = cast(
            Any,
            importlib.import_module("transformers.models.smolvlm.processing_smolvlm"),
        ).get_image_prompt_string
        texts: list[str] = []
        tiles: list[int] = []
        for i in range(len(frames)):
            r, c = feats["rows"][i][0], feats["cols"][i][0]
            n_tiles = r * c + 1 if r * c else 1
            real = int(feats["pixel_attention_mask"][i].flatten(1).any(dim=1).sum())
            if n_tiles != real:
                raise RuntimeError(f"caption glue: row {i}: expected {n_tiles} tiles, got {real}")
            text = expand_image_tokens(
                prompt_chat, get_prompt(r, c, self._seq, FAKE_TOKEN, IMAGE_TOKEN, GLOBAL_TOKEN)
            )
            if text.count(IMAGE_TOKEN) != n_tiles * self._seq:
                raise RuntimeError(
                    f"caption glue: row {i}: expected {n_tiles * self._seq} {IMAGE_TOKEN}, "
                    f"got {text.count(IMAGE_TOKEN)}"
                )
            texts.append(text)
            tiles.append(n_tiles)
        enc = self._tok(texts, return_tensors="pt", padding=True, add_special_tokens=True)
        return feats, enc, tiles

    def caption(self, frames: Sequence[Frame], prompt_id: str) -> list[Caption]:
        spec = PROMPTS.get(prompt_id)
        if spec is None:
            raise ValueError(f"unknown prompt id {prompt_id!r}")
        if not frames:
            return []
        torch = cast(Any, importlib.import_module("torch"))
        feats, enc, _ = self._prepare(frames, spec)
        dev = self._device
        torch.manual_seed(SEED)
        with torch.inference_mode():
            out = self._model.generate(
                input_ids=enc.input_ids.to(dev),
                attention_mask=enc.attention_mask.to(dev),
                pixel_values=feats["pixel_values"].to(dev),
                pixel_attention_mask=feats["pixel_attention_mask"].to(dev),
                do_sample=False,
                num_beams=1,
                max_new_tokens=spec.max_new_tokens,
            )
        eos = self._model.generation_config.eos_token_id
        stop: set[Any] = set(eos if isinstance(eos, list) else [eos])  # pyright: ignore[reportUnknownArgumentType]
        stop.add(self._tok.pad_token_id)
        start = int(enc.input_ids.shape[1])
        result: list[Caption] = []
        for j, frame in enumerate(frames):
            gen = [int(t) for t in out[j, start:].tolist()]
            n = next((k for k, t in enumerate(gen) if t in stop), len(gen))
            truncated = n == len(gen) == spec.max_new_tokens
            reply = self._tok.decode(gen[:n], skip_special_tokens=True)
            if is_prompt_echo(reply, spec.text):
                text, media = "", ()  # the model repeated its instructions: no caption
            else:
                text, media = parse_reply(reply, truncated=truncated)
            result.append(Caption(frame.t_s, text, None, media))
        return result
