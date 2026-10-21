"""Result records (spec 25, R1-R3, cards 2, 3 and 6). Pure value tests: no media, no models."""

import dataclasses
import json
import pickle
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tapesift.media.types import AssetInfo, AudioStreamInfo, VideoInfo
from tapesift.schema.records import (
    BACKEND_ID_RE,
    AssetRecord,
    Caption,
    Hit,
    Modality,
    Provenance,
    Utterance,
    Word,
    clamp_utterance,
)
from tapesift.warning_codes import AssetWarning, WarningCode

ASSET_ID = "tsid1:" + "0" * 64
SHA = "536b0662742c02347bc0e980a01041f333bce120"
ZEROS = "0" * 40
_VIDEO = VideoInfo(0, "h264", 320, 240, 25.0, vfr=False, rotation=0)

A_WARN = AssetWarning(WarningCode.LOW_SPEECH, "speech ratio 0.01")
B_WARN = AssetWarning(WarningCode.NO_AUDIO, "no audio stream")


def _asset(*, duration_s: float | None = 5.0, warnings: tuple[AssetWarning, ...] = ()) -> AssetInfo:
    return AssetInfo(ASSET_ID, Path("clip.mp4"), duration_s, _VIDEO, (), warnings)


def _utt(start_s: float = 1.0, end_s: float = 2.0, words: tuple[Word, ...] = ()) -> Utterance:
    return Utterance(start_s, end_s, "hello there", "en", 0.9, words)


def _prov() -> Provenance:
    return Provenance("0.1.0", None, None, None)


def _record(
    *,
    asset: AssetInfo | None = None,
    utterances: tuple[Utterance, ...] = (),
    captions: tuple[Caption, ...] = (),
    warnings: tuple[AssetWarning, ...] = (),
) -> AssetRecord:
    return AssetRecord(asset or _asset(), utterances, captions, warnings, _prov())


def _hit() -> Hit:
    return Hit(ASSET_ID, "a b.mp4", 1.5, 1.5, Modality.VISUAL, "a slide", ("BUY NOW",), 0.5)


# ---- construction rules ---------------------------------------------------


@pytest.mark.parametrize(
    ("make", "field"),
    [
        pytest.param(lambda: Word("a", 0.0, 1.0), "w", id="Word"),
        pytest.param(lambda: _utt(), "text", id="Utterance"),
        pytest.param(lambda: Caption(1.0, "x", 0.5, ()), "text", id="Caption"),
        pytest.param(lambda: Provenance("0.1.0", None, None, None), "tapesift", id="Provenance"),
        pytest.param(lambda: _record(), "utterances", id="AssetRecord"),
        pytest.param(lambda: _hit(), "score", id="Hit"),
    ],
)
def test_records_are_frozen(make: Callable[[], Any], field: str) -> None:
    obj = make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, getattr(obj, field))


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: Word("a", 2.0, 1.0), id="word_reversed"),
        pytest.param(lambda: Word("a", -1.0, 1.0), id="word_negative"),
        pytest.param(lambda: Word("a", float("nan"), 1.0), id="word_nan"),
        pytest.param(lambda: _utt(1.0, float("inf")), id="utterance_inf_end"),
        pytest.param(lambda: Caption(-1.0, "x", None, ()), id="caption_negative_t"),
        pytest.param(lambda: Caption(float("nan"), "x", None, ()), id="caption_nan_t"),
    ],
)
def test_bad_span_rejected(make: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        make()


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: Utterance(1.0, 2.0, "x", "en", -0.01, ()), id="utterance_below"),
        pytest.param(lambda: Utterance(1.0, 2.0, "x", "en", 1.01, ()), id="utterance_above"),
        pytest.param(lambda: Caption(1.0, "x", float("nan"), ()), id="caption_nan"),
        pytest.param(lambda: Caption(1.0, "x", 1.5, ()), id="caption_above"),
    ],
)
def test_conf_out_of_range_rejected(make: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        make()


def test_caption_conf_may_be_none() -> None:
    assert Caption(1.0, "x", None, ()).conf is None


@pytest.mark.parametrize(
    "words",
    [
        pytest.param((Word("a", 0.5, 1.5),), id="word_before_start"),
        pytest.param((Word("a", 2.5, 3.5),), id="word_after_end"),
        pytest.param((Word("b", 2.0, 2.5), Word("a", 1.0, 1.5)), id="words_unsorted"),
    ],
)
def test_words_must_sit_inside_their_utterance(words: tuple[Word, ...]) -> None:
    with pytest.raises(ValueError):
        Utterance(1.0, 3.0, "x", "en", 0.9, words)


# ---- AssetRecord ----------------------------------------------------------


def test_asset_record_merges_and_sorts_warnings() -> None:
    rec = _record(asset=_asset(warnings=(B_WARN,)), warnings=(B_WARN, A_WARN))
    assert rec.warnings == (A_WARN, B_WARN)


@pytest.mark.parametrize(
    ("utterances", "captions"),
    [
        pytest.param((_utt(2.0, 3.0), _utt(1.0, 1.5)), (), id="utterances_unsorted"),
        pytest.param(
            (), (Caption(1.0, "a", None, ()), Caption(1.0, "b", None, ())), id="captions_equal_t"
        ),
        pytest.param((_utt(4.0, 5.01),), (), id="utterance_end_past_duration"),
        pytest.param((), (Caption(5.0, "a", None, ()),), id="caption_at_duration"),
    ],
)
def test_asset_record_rejects_bad_timeline(
    utterances: tuple[Utterance, ...], captions: tuple[Caption, ...]
) -> None:
    with pytest.raises(ValueError):
        _record(utterances=utterances, captions=captions)


@given(end_s=st.floats(min_value=1.0, max_value=1e12))
def test_asset_record_allows_unknown_duration(end_s: float) -> None:
    rec = _record(asset=_asset(duration_s=None), utterances=(_utt(0.0, end_s),))
    assert rec.utterances[0].end_s == end_s


# ---- Provenance -----------------------------------------------------------


@pytest.mark.parametrize(
    ("backend_id", "ok"),
    [
        pytest.param(f"faster-whisper:small@{SHA}", True, id="whisper_ok"),
        pytest.param(f"onnx:bge-small-en-v1.5@{SHA}", True, id="onnx_ok"),
        pytest.param("openai:Qwen/Qwen2-VL-2B-Instruct@unpinned", True, id="endpoint_unpinned_ok"),
        pytest.param(f"fake:asr@{ZEROS}", True, id="fake_ok"),
        pytest.param(f"small@{SHA}", False, id="no_backend"),
        pytest.param("faster-whisper:small", False, id="no_revision"),
        pytest.param("Faster-Whisper:small@unpinned", False, id="uppercase_backend"),
        pytest.param("faster-whisper:sm all@unpinned", False, id="space"),
        pytest.param("faster-whisper:small@536b0662742c", False, id="short_sha"),
        pytest.param("openai:m@Unpinned", False, id="unpinned_wrong_case"),
        pytest.param("x:y@unpinned", True, id="unpinned_exact"),
        pytest.param("x:y@unpinned-extra", False, id="unpinned_suffix"),
        pytest.param("x:y@unpinned1", False, id="unpinned_digit_suffix"),
    ],
)
def test_provenance_backend_id(backend_id: str, ok: bool) -> None:
    if ok:
        assert BACKEND_ID_RE.fullmatch(backend_id)
        assert Provenance("0.1.0", backend_id, None, None).asr == backend_id
    else:
        assert not BACKEND_ID_RE.fullmatch(backend_id)
        with pytest.raises(ValueError):
            Provenance("0.1.0", backend_id, None, None)


@pytest.mark.parametrize(
    ("vlm", "prompt"),
    [
        pytest.param(f"fake:vlm@{ZEROS}", None, id="vlm_without_prompt"),
        pytest.param(None, "caption_v1", id="prompt_without_vlm"),
    ],
)
def test_provenance_vlm_and_prompt_set_together(vlm: str | None, prompt: str | None) -> None:
    with pytest.raises(ValueError):
        Provenance("0.1.0", None, vlm, prompt)


# ---- Hit and Modality -----------------------------------------------------


def test_hit_json_shape() -> None:
    hit = Hit(ASSET_ID, "a b.mp4", 1.5, 1.5, Modality.VISUAL, "a slide", ("BUY NOW",), 0.5)
    assert json.dumps(asdict(hit)) == (
        '{"asset_id": "tsid1:' + "0" * 64 + '", "path": "a b.mp4", "start_s": 1.5, "end_s": 1.5, '
        '"modality": "visual", "text": "a slide", "media_text": ["BUY NOW"], "score": 0.5, '
        '"trust": "untrusted_media"}'
    )


def test_modality_values() -> None:
    assert [m.value for m in Modality] == ["speech", "visual"]


def test_records_pickle_round_trip() -> None:
    asset = AssetInfo(
        ASSET_ID,
        Path("clip.mp4"),
        5.0,
        _VIDEO,
        (AudioStreamInfo(1, "aac", "eng", True),),
        (B_WARN,),
    )
    rec = AssetRecord(
        asset,
        (_utt(1.0, 2.0, (Word("hello", 1.0, 1.5), Word("there", 1.5, 2.0))),),
        (Caption(1.0, "a slide", 0.7, ("BUY NOW",)),),
        (A_WARN,),
        Provenance("0.1.0", f"faster-whisper:small@{SHA}", f"fake:vlm@{ZEROS}", "caption_v1"),
    )
    assert pickle.loads(pickle.dumps(rec)) == rec  # noqa: S301


def test_interface_modules_import_no_backends() -> None:
    code = (
        "import sys, tapesift.config, tapesift.hub, tapesift.schema.records, "
        "tapesift.audio.types, tapesift.vision.types, tapesift.store.types\n"
        "banned = {'torch', 'transformers', 'ctranslate2', 'faster_whisper', 'lancedb', "
        "'pyarrow', 'onnxruntime', 'tokenizers', 'huggingface_hub', 'av'}\n"
        "print(sorted(banned & set(sys.modules)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert out.stdout.strip() == "[]"


# ---- clamp_utterance ------------------------------------------------------


def _w(start_s: float, end_s: float) -> Word:
    return Word("w", start_s, end_s)


@pytest.mark.parametrize(
    ("u", "lo", "hi", "expected"),
    [
        pytest.param(_utt(1.0, 2.0), 0.0, 3.0, _utt(1.0, 2.0), id="inside"),
        pytest.param(
            _utt(2.5, 3.04, (_w(2.5, 2.9), _w(2.9, 3.04))),
            0.0,
            3.0,
            _utt(2.5, 3.0, (_w(2.5, 2.9), _w(2.9, 3.0))),
            id="end_overshoot",
        ),
        pytest.param(
            _utt(0.5, 1.5, (_w(0.5, 1.0), _w(1.0, 1.5))),
            1.0,
            3.0,
            _utt(1.0, 1.5, (_w(1.0, 1.0), _w(1.0, 1.5))),
            id="start_before_lo",
        ),
        pytest.param(
            _utt(2.0, 3.2, (_w(2.0, 2.9), _w(3.01, 3.2))),
            0.0,
            3.0,
            _utt(2.0, 3.0, (_w(2.0, 2.9),)),
            id="word_past_hi_dropped",
        ),
        pytest.param(_utt(3.0, 3.5), 0.0, 3.0, None, id="entirely_after"),
        pytest.param(_utt(0.2, 0.5), 1.0, 3.0, None, id="entirely_before"),
        pytest.param(_utt(0.5, 1.0), 1.0, 3.0, _utt(1.0, 1.0), id="end_equals_lo_kept"),
    ],
)
def test_clamp_utterance(u: Utterance, lo: float, hi: float, expected: Utterance | None) -> None:
    assert clamp_utterance(u, lo, hi) == expected


@pytest.mark.parametrize(
    ("lo", "hi"),
    [pytest.param(3.0, 1.0, id="lo_above_hi"), pytest.param(0.0, float("nan"), id="hi_nan")],
)
def test_clamp_rejects_bad_bounds(lo: float, hi: float) -> None:
    with pytest.raises(ValueError):
        clamp_utterance(_utt(), lo, hi)
