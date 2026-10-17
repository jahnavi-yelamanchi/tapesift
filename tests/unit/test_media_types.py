import dataclasses
import inspect
import itertools
import pickle
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from tapesift.media.types import (
    AUDIO_GAP_FILL_S,
    EARLY_EOF_S,
    MAX_GAP_WARNINGS,
    MAX_SIDE_PX,
    SHORT_CLIP_S,
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
_VIDEO = VideoInfo(0, "h264", 320, 240, 25.0, vfr=False, rotation=0)


def _asset(
    *,
    path: Path = Path("clip.mp4"),
    audio: tuple[AudioStreamInfo, ...] = (),
    warnings: tuple[AssetWarning, ...] = (),
    video: VideoInfo | None = _VIDEO,
    duration_s: float | None = 2.0,
) -> AssetInfo:
    return AssetInfo("tsid1:" + "0" * 64, path, duration_s, video, audio, warnings)


def _track(index: int, *, default: bool = False) -> AudioStreamInfo:
    return AudioStreamInfo(index, "aac", "eng", default)


@pytest.mark.parametrize(
    ("err", "text"),
    [
        (ProbeError(WarningCode.UNREADABLE, "x"), "UNREADABLE: x"),
        (DecodeError(WarningCode.UNSUPPORTED_CODEC, "x"), "UNSUPPORTED_CODEC: x"),
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


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (ProbeError, WarningCode.UNSUPPORTED_CODEC),
        (ProbeError, WarningCode.PARTIAL_DECODE),
        (DecodeError, WarningCode.PARTIAL_DECODE),
        (DecodeError, WarningCode.VFR_DETECTED),
    ],
)
def test_stage_errors_reject_codes_outside_their_stage(
    cls: type[StageError], code: WarningCode
) -> None:
    with pytest.raises(ValueError):
        cls(code, "x")


def test_decode_error_accepts_unreadable() -> None:
    assert DecodeError(WarningCode.UNREADABLE, "x").warning.code is WarningCode.UNREADABLE


def test_frame_copies_borrowed_pixels() -> None:
    base = np.zeros((4, 2, 3), np.uint8)
    frame = Frame(0.0, base[:2])
    base[:] = 7
    assert not frame.pixels.any()
    assert base.flags.writeable


def test_frame_stays_read_only_after_pickle() -> None:
    frame = Frame(1.5, np.arange(12, dtype=np.uint8).reshape(2, 2, 3))
    back = pickle.loads(pickle.dumps(frame))  # noqa: S301
    assert back.pixels.flags.writeable is False
    assert back.t_s == frame.t_s
    assert np.array_equal(back.pixels, frame.pixels)


def _samples(n: int = 4) -> np.ndarray:
    return np.zeros(n, dtype=np.float32)


@pytest.mark.parametrize(
    ("start_s", "samples", "sample_rate"),
    [
        (0.0, np.zeros((2, 2), dtype=np.float32), 16_000),
        (0.0, np.zeros(4, dtype=np.float64), 16_000),
        (0.0, _samples(0), 16_000),
        (0.0, _samples(), 0),
        (0.0, _samples(), -1),
        (float("nan"), _samples(), 16_000),
        (float("inf"), _samples(), 16_000),
    ],
    ids=["2d", "float64", "empty", "rate0", "rate-1", "start-nan", "start-inf"],
)
def test_audio_chunk_rejects_bad_input(
    start_s: float, samples: np.ndarray, sample_rate: int
) -> None:
    with pytest.raises(ValueError):
        AudioChunk(start_s, samples, sample_rate)


def test_audio_chunk_samples_are_read_only() -> None:
    chunk = AudioChunk(0.0, _samples(), 16_000)
    with pytest.raises(ValueError, match="read-only"):
        chunk.samples[0] = 1.0


def test_audio_chunk_copies_borrowed_samples() -> None:
    base = _samples()
    chunk = AudioChunk(0.0, base[:2], 16_000)
    base[:] = 7
    assert not chunk.samples.any()
    assert base.flags.writeable


def test_audio_chunk_stays_read_only_after_pickle() -> None:
    chunk = AudioChunk(0.5, np.arange(4, dtype=np.float32), 16_000)
    back = pickle.loads(pickle.dumps(chunk))  # noqa: S301
    assert back.samples.flags.writeable is False
    assert (back.start_s, back.sample_rate) == (chunk.start_s, chunk.sample_rate)
    assert np.array_equal(back.samples, chunk.samples)


def test_warnings_sort_by_code_then_detail() -> None:
    a = AssetWarning(WarningCode.NO_AUDIO, "a")
    b = AssetWarning(WarningCode.NO_AUDIO, "b")
    c = AssetWarning(WarningCode.ROTATED, "a")
    for perm in itertools.permutations((c, b, a, b)):
        assert _asset(warnings=perm).warnings == (a, b, c)


def test_default_audio_picks_first_default_flagged() -> None:
    tracks = (_track(1), _track(2, default=True), _track(3, default=True))
    assert _asset(audio=tracks).default_audio is tracks[1]


def test_constants_and_iter_audio_defaults() -> None:
    assert (MAX_SIDE_PX, SHORT_CLIP_S, AUDIO_GAP_FILL_S) == (768, 1.0, 0.5)
    assert (MAX_GAP_WARNINGS, EARLY_EOF_S) == (20, 1.0)
    params = inspect.signature(Decoder.iter_audio).parameters
    assert params["sample_rate"].default == 16_000
    assert params["chunk_s"].default == 600.0
    assert params["track"].default is None


def test_asset_info_audio_only_and_unknown_duration() -> None:
    track = _track(0)
    audio_only = _asset(video=None, audio=(track,))
    assert audio_only.video is None
    assert audio_only.default_audio is track
    silent = _asset(duration_s=None)
    assert silent.default_audio is None
    assert silent.duration_s is None


_MEDIA_MAGIC = (
    b"\x1aE\xdf\xa3",
    b"ID3",
    b"RIFF",
    b"OggS",
    b"fLaC",
    b"\xff\xfb",
    b"\x00\x00\x01\xba",
    b"\x00\x00\x01\xb3",
    b"FLV",
)


def test_not_media_fixture_is_plain_text() -> None:
    data = (FIXTURES / "not_media.txt").read_bytes()
    assert data.isascii()
    data.decode("ascii")
    assert not data.startswith(_MEDIA_MAGIC)
    assert data[4:8] != b"ftyp"
