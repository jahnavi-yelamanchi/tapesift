import dataclasses
import pickle
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from tapesift.media.types import (
    AssetInfo,
    AudioChunk,
    AudioStreamInfo,
    DecodeError,
    Decoder,
    Frame,
    ProbeError,
    VideoInfo,
)
from tapesift.warning_codes import AssetWarning, StageError, WarningCode, WarningSink

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _asset(
    *,
    path: Path = Path("clip.mp4"),
    audio: tuple[AudioStreamInfo, ...] = (),
    warnings: tuple[AssetWarning, ...] = (),
) -> AssetInfo:
    video = VideoInfo(0, "h264", 320, 240, 25.0, vfr=False, rotation=0)
    return AssetInfo("tsid1:" + "0" * 64, path, 2.0, video, audio, warnings)


def _track(index: int, *, default: bool = False) -> AudioStreamInfo:
    return AudioStreamInfo(index, "aac", "eng", default)


@pytest.mark.parametrize(
    ("err", "text"),
    [
        (ProbeError(WarningCode.UNREADABLE, "x"), "UNREADABLE: x"),
        (DecodeError(WarningCode.PARTIAL_DECODE, "x"), "PARTIAL_DECODE: x"),
    ],
)
def test_stage_errors_round_trip_through_pickle(err: StageError, text: str) -> None:
    back = pickle.loads(pickle.dumps(err))  # noqa: S301
    assert type(back) is type(err)
    assert isinstance(back, StageError)
    assert back.warning == err.warning
    assert str(back) == text


def test_asset_info_is_immutable() -> None:
    asset = _asset()
    with pytest.raises(dataclasses.FrozenInstanceError):
        asset.duration_s = 1.0  # pyright: ignore[reportAttributeAccessIssue]


def test_asset_info_normalizes_warnings() -> None:
    a = AssetWarning(WarningCode.NO_AUDIO, "no audio stream")
    b = AssetWarning(WarningCode.ROTATED, "rotation 90")
    assert _asset(warnings=(b, a, b)).warnings == (a, b)


def test_asset_info_keeps_unicode_path() -> None:
    asset = _asset(path=FIXTURES / "réunion 01.mp4")
    assert pickle.loads(pickle.dumps(asset)) == asset  # noqa: S301
    assert asset.path.exists()


def test_default_audio_rule() -> None:
    assert _asset().default_audio is None
    plain = (_track(1), _track(2))
    assert _asset(audio=plain).default_audio == plain[0]
    flagged = (_track(1), _track(2, default=True))
    assert _asset(audio=flagged).default_audio == flagged[1]


def test_frame_pixels_are_read_only() -> None:
    frame = Frame(0.0, np.zeros((2, 2, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="read-only"):
        frame.pixels[0, 0, 0] = 1


def test_frame_requires_contiguous_pixels() -> None:
    a = np.zeros((2, 3, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="C-contiguous"):
        Frame(0.0, np.rot90(a))
    assert Frame(0.0, np.ascontiguousarray(np.rot90(a))).pixels.shape == (3, 2, 3)


def test_asset_warning_rejects_plain_str() -> None:
    with pytest.raises(TypeError):
        AssetWarning("VFR_DETECTED", "x")  # pyright: ignore[reportArgumentType]


def test_arrays_compare_by_identity() -> None:
    def pixels() -> np.ndarray:
        return np.zeros((2, 2, 3), dtype=np.uint8)

    def samples() -> np.ndarray:
        return np.zeros(4, dtype=np.float32)

    assert (Frame(0.0, pixels()) == Frame(0.0, pixels())) is False
    assert (AudioChunk(0.0, samples(), 16_000) == AudioChunk(0.0, samples(), 16_000)) is False


def test_types_do_not_import_av() -> None:
    code = "import sys, tapesift.warning_codes, tapesift.media.types; print('av' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=30
    )
    assert out.stdout.strip() == "False"


class _FakeDecoder:
    def iter_frames(
        self, asset: AssetInfo, every_s: float | None, *, warn: WarningSink
    ) -> Iterator[Frame]:
        yield Frame(0.0, np.zeros((2, 2, 3), dtype=np.uint8))

    def iter_audio(
        self,
        asset: AssetInfo,
        sample_rate: int = 16_000,
        *,
        track: int | None = None,
        chunk_s: float = 600.0,
        warn: WarningSink,
    ) -> Iterator[AudioChunk]:
        yield AudioChunk(0.0, np.zeros(1, dtype=np.float32), sample_rate)


def test_fake_decoder_satisfies_protocol() -> None:
    decoder: Decoder = _FakeDecoder()
    warnings: list[AssetWarning] = []
    frame = next(decoder.iter_frames(_asset(), None, warn=warnings.append))
    assert frame.pixels.dtype == np.uint8
