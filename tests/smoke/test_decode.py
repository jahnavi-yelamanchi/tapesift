"""Issue #6: CPU decode with PyAV. docs/specs/6-decode.md, Acceptance rows 1-19.
Each row's tests share the `-k` prefix named in the spec table."""

import itertools
import math
import re
import shutil
import socket
import subprocess
import sys
import threading
import tracemalloc
import wave
from collections.abc import Callable, Generator, Iterator
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast

import av
import numpy as np
import pytest
from av.error import InvalidDataError
from conftest import FIXTURES
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from tapesift.media.types import (
    AUDIO_GAP_FILL_S,
    EARLY_EOF_S,
    MAX_GAP_WARNINGS,
    MAX_SIDE_PX,
    AssetInfo,
    AudioChunk,
    AudioStreamInfo,
    DecodeError,
    Decoder,
    Frame,
    VideoInfo,
)
from tapesift.warning_codes import AssetWarning, WarningCode, WarningSink

# ruff sorts the module under test as first-party only once decode.py exists; its own block
# keeps the import order valid before and after.
# isort: split
from tapesift.media.decode import (
    GapState,
    Placement,
    PyAVDecoder,
    chunk_runs,
    clamp_run,
    clock_s,
    frame_kept,
    gap_on_eof,
    gap_on_fail,
    gap_on_flush,
    gap_on_good,
    gap_summary,
    gap_warning,
    half_up,
    place_audio,
    upright_size,
    window_index,
)

# ---- hand-built assets (spec table; E1 is built in parallel, so no probe) ----

_ID = "tsid1:" + "0" * 64
_AAC = (AudioStreamInfo(1, "aac", "und", True),)


def _asset(
    path: Path,
    duration_s: float | None,
    video: VideoInfo | None,
    audio: tuple[AudioStreamInfo, ...] = (),
) -> AssetInfo:
    return AssetInfo(_ID, path, duration_s, video, audio, ())


CLEAN = _asset(FIXTURES / "clean.mp4", 5.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0), _AAC)
VFR = _asset(FIXTURES / "vfr.mp4", 5.933333, VideoInfo(0, "h264", 320, 240, 1500 / 89, True, 0))
START_OFFSET = _asset(
    FIXTURES / "start_offset.mp4", 5.52, VideoInfo(0, "h264", 320, 240, 25.0, False, 0), _AAC
)
MULTI_AUDIO = _asset(
    FIXTURES / "multi_audio.mkv",
    3.064,
    VideoInfo(0, "h264", 320, 240, 25.0, False, 0),
    (AudioStreamInfo(1, "aac", "eng", True), AudioStreamInfo(2, "aac", "eng", False)),
)
ROTATED = _asset(
    FIXTURES / "rotated.mp4", 5.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 90), _AAC
)
ROTATED_270 = _asset(
    FIXTURES / "rotated_270.mp4", 1.0, VideoInfo(0, "h264", 320, 240, 5.0, False, 270)
)
UHD_4K = _asset(FIXTURES / "uhd_4k.mp4", 1.0, VideoInfo(0, "h264", 3840, 2160, 5.0, False, 0))
HDR10 = _asset(FIXTURES / "hdr10.mkv", 2.0, VideoInfo(0, "hevc", 320, 240, 25.0, False, 0))
TRUNCATED = _asset(
    FIXTURES / "truncated.mp4", 6.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0), _AAC
)
AV_MISMATCH = _asset(
    FIXTURES / "av_mismatch.mp4", 3.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0), _AAC
)
NO_AUDIO = _asset(FIXTURES / "no_audio.mp4", 3.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0))
PRORES = _asset(FIXTURES / "prores.mov", 1.0, VideoInfo(0, "prores", 160, 120, 10.0, False, 0))
UNKNOWN_CODEC = _asset(
    FIXTURES / "unknown_codec.mov", 1.0, VideoInfo(0, "unknown", None, None, 25.0, False, 0)
)
NOT_MEDIA = _asset(
    FIXTURES / "not_media.txt", None, VideoInfo(0, "unknown", None, None, None, False, 0)
)
LONG_3H = _asset(FIXTURES / "long_3h.mp4", 10800.0, VideoInfo(0, "h264", 64, 36, 1.0, False, 0))
REUNION = _asset(
    FIXTURES / "réunion 01.mp4", 2.0, VideoInfo(0, "h264", 240, 160, 25.0, False, 0), _AAC
)
BAD_INDEX = _asset(
    FIXTURES / "clean.mp4",
    5.0,
    VideoInfo(5, "h264", 320, 240, 25.0, False, 0),
    (AudioStreamInfo(7, "aac", "und", True),),
)
FAKE_AUDIO = _asset(FIXTURES / "clean.mp4", 5.0, None, (AudioStreamInfo(1, "unknown", None, True),))

_FIXTURE_ASSETS = (
    CLEAN,
    VFR,
    START_OFFSET,
    MULTI_AUDIO,
    ROTATED,
    ROTATED_270,
    UHD_4K,
    HDR10,
    TRUNCATED,
    AV_MISMATCH,
    NO_AUDIO,
    PRORES,
    UNKNOWN_CODEC,
    NOT_MEDIA,
    LONG_3H,
    REUNION,
)

D = PyAVDecoder()
_PROP = settings(max_examples=200, deadline=None, derandomize=True)


@pytest.fixture
def sink() -> list[AssetWarning]:
    return []


def _partials(sink: list[AssetWarning]) -> list[AssetWarning]:
    return [w for w in sink if w.code is WarningCode.PARTIAL_DECODE]


def _frames(asset: AssetInfo, every_s: float | None, sink: list[AssetWarning]) -> list[Frame]:
    return list(D.iter_frames(asset, every_s, warn=sink.append))


def _first_frame(asset: AssetInfo) -> Frame:
    warnings: list[AssetWarning] = []
    return next(D.iter_frames(asset, None, warn=warnings.append))


def _joined(chunks: list[AudioChunk]) -> NDArray[np.float32]:
    return np.concatenate([c.samples for c in chunks])


def _spectrum(samples: NDArray[np.float32], sample_rate: int) -> tuple[NDArray[Any], NDArray[Any]]:
    mag = np.abs(np.fft.rfft(samples.astype(np.float64)))
    mag[0] = 0.0  # ignore DC
    return np.fft.rfftfreq(samples.size, 1 / sample_rate), mag


def _peak_hz(samples: NDArray[np.float32], sample_rate: int) -> float:
    freqs, mag = _spectrum(samples, sample_rate)
    return float(freqs[np.argmax(mag)])


def _check_chunks(chunks: list[AudioChunk], sample_rate: int, chunk_n: int) -> None:
    assert chunks
    for c in chunks:
        assert c.samples.dtype == np.float32
        assert c.samples.ndim == 1
        assert c.sample_rate == sample_rate
        assert float(c.samples.min()) >= -1.0
        assert float(c.samples.max()) <= 1.0
    assert all(c.samples.size == chunk_n for c in chunks[:-1])
    for prev, nxt in itertools.pairwise(chunks):
        assert nxt.start_s == pytest.approx(prev.start_s + prev.samples.size / sample_rate)


# ---- row 1: the hand-built table matches the manifest ----


def test_assets_match_manifest(manifest: Any) -> None:
    names = {e["name"] for e in manifest["fixtures"]}
    assert len({a.path.name for a in _FIXTURE_ASSETS}) == 16
    for asset in _FIXTURE_ASSETS:
        assert asset.path.parent == FIXTURES
        assert asset.path.name in names
        assert asset.id == _ID
        assert asset.warnings == ()


# ---- row 2: Protocol conformance ----


def test_protocol_conformance(sink: list[AssetWarning]) -> None:
    decoder: Decoder = PyAVDecoder()
    assert isinstance(next(decoder.iter_frames(CLEAN, None, warn=sink.append)), Frame)


# ---- row 3: R1, R7: VFR times come from PTS ----

_VFR_PTS = (
    [i * 0.1 for i in range(20)]
    + [2 + i / 30 for i in range(60)]
    + [4 + i * 0.1 for i in range(20)]
)


def test_vfr_times_come_from_pts(sink: list[AssetWarning]) -> None:
    frames = _frames(VFR, None, sink)
    assert len(frames) == 100
    for frame, expected in zip(frames, _VFR_PTS, strict=True):
        assert abs(frame.t_s - expected) <= 1 / 30


def test_vfr_every_half_second(sink: list[AssetWarning]) -> None:
    frames = _frames(VFR, 0.5, sink)
    assert len(frames) == 12
    for k, frame in enumerate(frames):
        assert frame.t_s == pytest.approx(k * 0.5, abs=1 / 30)


def test_vfr_empty_windows_yield_nothing(sink: list[AssetWarning]) -> None:
    frames = _frames(VFR, 0.05, sink)
    assert len(frames) == 80
    ks = [window_index(f.t_s, 0.05) for f in frames]
    assert all(a < b for a, b in itertools.pairwise(ks))


# ---- row 4: R1: container-clock normalization ----


def test_start_offset_video_and_audio(sink: list[AssetWarning]) -> None:
    first = next(D.iter_frames(START_OFFSET, None, warn=sink.append))
    assert abs(first.t_s - 1.52) <= 0.04
    chunk = next(D.iter_audio(START_OFFSET, warn=sink.append))
    assert 0.0 <= chunk.start_s <= 0.002


def test_start_negative_container_start(sink: list[AssetWarning]) -> None:
    first = next(D.iter_frames(MULTI_AUDIO, None, warn=sink.append))
    # Owner ruling (#6, 2026-10-17): PyAV 19.0.1 (FFmpeg 9.0.2) reports this container's
    # start_time as 0, while ffprobe 7.1.1 says -0.064; PyAV is what we decode with.
    assert first.t_s == pytest.approx(0.0, abs=0.002)


# ---- row 5: R5: rotation with no resize, pixel-exact ----


def test_rotated_90_matches_rot90_of_clean() -> None:
    rotated = _first_frame(ROTATED).pixels
    assert rotated.shape == (320, 240, 3)
    assert np.array_equal(rotated, np.rot90(_first_frame(CLEAN).pixels, 1))


def test_rotated_270_red_right_blue_left() -> None:
    pixels = _first_frame(ROTATED_270).pixels
    assert pixels.shape == (320, 240, 3)
    red = pixels[160, 230].astype(int)
    blue = pixels[160, 10].astype(int)
    assert red[0] > 200
    assert red[2] < 60
    assert blue[2] > 200
    assert blue[0] < 60


# ---- row 6: R6: the resize path ----


def test_downscale_uhd_to_768(sink: list[AssetWarning]) -> None:
    frames = _frames(UHD_4K, None, sink)
    assert len(frames) == 5
    for f in frames:
        assert f.pixels.shape == (432, 768, 3)
        assert f.pixels.dtype == np.uint8


def test_downscale_never_upscales(sink: list[AssetWarning]) -> None:
    frames = _frames(CLEAN, None, sink)
    assert frames
    assert all(f.pixels.shape == (240, 320, 3) for f in frames)


# ---- row 7: 8-bit from 10-bit PQ ----


def test_hdr_to_8bit(sink: list[AssetWarning]) -> None:
    frames = _frames(HDR10, None, sink)
    assert len(frames) == 50
    for f in frames:
        assert f.pixels.shape == (240, 320, 3)
        assert f.pixels.dtype == np.uint8
    assert sink == []


# ---- row 8: pixels own their memory ----


def test_pixels_own_their_memory(sink: list[AssetWarning]) -> None:
    for asset in (CLEAN, ROTATED, UHD_4K):
        frames = D.iter_frames(asset, None, warn=sink.append)
        first = next(frames)
        px = first.pixels
        assert px.base is None
        assert px.flags.owndata
        assert px.flags.c_contiguous
        assert not px.flags.writeable
        # M0's Frame copies views, so also check the decoder hands out fresh buffers:
        # holding a frame while decoding more must not change it, and frames never alias.
        snapshot = px.copy()
        prev = first
        more = 0
        for frame in itertools.islice(frames, 4):
            assert not np.shares_memory(prev.pixels, frame.pixels)
            prev = frame
            more += 1
        assert more == 4
        assert np.array_equal(first.pixels, snapshot)


# ---- row 9: Unicode path, passed to av.open as str ----


def test_unicode_path_passed_as_str(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    real_open = av.open
    seen: list[bool] = []

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(isinstance(file, str))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(av, "open", spy)
    frames = _frames(REUNION, None, sink)
    assert seen
    assert all(seen)
    assert len(frames) == 50
    assert all(f.pixels.shape == (160, 240, 3) for f in frames)


# ---- row 10: R8 on real audio ----


def test_audio_clean_16k(sink: list[AssetWarning]) -> None:
    chunks = list(D.iter_audio(CLEAN, 16_000, chunk_s=1.0, warn=sink.append))
    _check_chunks(chunks, 16_000, 16_000)
    samples = _joined(chunks)
    assert 78_976 <= samples.size <= 80_000
    assert abs(_peak_hz(samples, 16_000) - 440) <= 2


def test_audio_clean_8k(sink: list[AssetWarning]) -> None:
    chunks = list(D.iter_audio(CLEAN, 8000, chunk_s=1.0, warn=sink.append))
    _check_chunks(chunks, 8000, 8000)
    samples = _joined(chunks)
    assert 38_976 <= samples.size <= 40_000
    assert abs(_peak_hz(samples, 8000) - 440) <= 2


def test_audio_trimmed_at_video_end(sink: list[AssetWarning]) -> None:
    chunks = list(D.iter_audio(AV_MISMATCH, warn=sink.append))
    assert chunks
    assert 46_976 <= sum(c.samples.size for c in chunks) <= 48_000
    last = chunks[-1]
    assert last.start_s + (last.samples.size - 1) / 16_000 < 3.0


def test_audio_none_when_no_track(sink: list[AssetWarning]) -> None:
    assert list(D.iter_audio(NO_AUDIO, warn=sink.append)) == []
    assert sink == []


# ---- row 11: track selection ----


@pytest.mark.parametrize(("track", "hz"), [(None, 440), (1, 660)])
def test_tracks_select_stream(track: int | None, hz: int, sink: list[AssetWarning]) -> None:
    chunks = list(D.iter_audio(MULTI_AUDIO, track=track, warn=sink.append))
    assert abs(_peak_hz(_joined(chunks), 16_000) - hz) <= 2


# ---- row 12: downmix and resample from stereo 44.1 kHz ----


def _write_stereo_wav(path: Path) -> None:
    rate = 44_100
    t = np.arange(rate) / rate
    left = 0.4 * np.sin(2 * np.pi * 440 * t)
    right = 0.4 * np.sin(2 * np.pi * 1000 * t)
    data = np.round(np.stack([left, right], axis=1) * 32767).astype("<i2")
    with path.open("wb") as fh, wave.open(fh, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def test_downmix_stereo_44k(tmp_path: Path, sink: list[AssetWarning]) -> None:
    path = tmp_path / "stereo.wav"
    _write_stereo_wav(path)
    stereo = _asset(path, 1.0, None, (AudioStreamInfo(0, "pcm_s16le", None, True),))
    chunks = list(D.iter_audio(stereo, warn=sink.append))
    assert chunks
    for c in chunks:
        assert c.samples.dtype == np.float32
        assert c.samples.ndim == 1
        assert c.sample_rate == 16_000
    samples = _joined(chunks)
    assert 15_000 <= samples.size <= 16_000
    freqs, mag = _spectrum(samples, 16_000)
    largest = float(mag.max())
    for hz in (440, 1000):
        band = mag[(freqs >= hz - 2) & (freqs <= hz + 2)]
        assert float(band.max()) >= 0.25 * largest


# ---- row 13: R10: damaged media and unreadable files ----


def test_corrupt_truncated_video(sink: list[AssetWarning]) -> None:
    frames = _frames(TRUNCATED, None, sink)
    assert len(frames) >= 75
    ts = [f.t_s for f in frames]
    assert all(a < b for a, b in itertools.pairwise(ts))
    assert 3.0 <= ts[-1] <= 3.3
    partial = _partials(sink)
    assert len(partial) == 1
    m = re.fullmatch(r"video stream 0: undecodable (\d+\.\d\d)-6\.00 s", partial[0].detail)
    assert m is not None
    assert m.group(1) == f"{ts[-1]:.2f}"


def test_corrupt_truncated_audio(sink: list[AssetWarning]) -> None:
    chunks = list(D.iter_audio(TRUNCATED, warn=sink.append))
    assert 1 <= sum(c.samples.size for c in chunks) <= 95_999
    partial = _partials(sink)
    assert len(partial) == 1
    assert re.fullmatch(r"audio stream 1: undecodable \d+\.\d\d-6\.00 s", partial[0].detail)


def test_corrupt_sink_exception_propagates() -> None:
    err = RuntimeError("sink")

    def raiser(warning: AssetWarning) -> None:
        raise err

    with pytest.raises(RuntimeError) as info:
        list(D.iter_frames(TRUNCATED, None, warn=raiser))
    assert info.value is err


def test_corrupt_not_media_unreadable(sink: list[AssetWarning]) -> None:
    with pytest.raises(DecodeError) as info:
        next(D.iter_frames(NOT_MEDIA, None, warn=sink.append))
    assert info.value.warning.code is WarningCode.UNREADABLE


def test_corrupt_gone_file_unreadable(tmp_path: Path, sink: list[AssetWarning]) -> None:
    path = tmp_path / "gone.mp4"
    shutil.copyfile(CLEAN.path, path)
    gone = _asset(path, CLEAN.duration_s, CLEAN.video, CLEAN.audio)
    path.unlink()
    with pytest.raises(DecodeError) as video:
        next(D.iter_frames(gone, None, warn=sink.append))
    assert video.value.warning.code is WarningCode.UNREADABLE
    with pytest.raises(DecodeError) as audio:
        next(D.iter_audio(gone, warn=sink.append))
    assert audio.value.warning.code is WarningCode.UNREADABLE


# ---- row 14: R10: a stream without a decoder gives UNSUPPORTED_CODEC ----


def test_codec_unknown_video_unsupported(sink: list[AssetWarning]) -> None:
    with pytest.raises(DecodeError) as info:
        next(D.iter_frames(UNKNOWN_CODEC, None, warn=sink.append))
    assert info.value.warning.code is WarningCode.UNSUPPORTED_CODEC
    assert "video stream 0" in info.value.warning.detail


class _FakeContainer:
    """Stand-in for av.open's result: stream 1 is audio with no decoder."""

    start_time = 0
    duration = 5_000_000

    def __init__(self) -> None:
        self.streams = [
            SimpleNamespace(type="video", index=0),
            SimpleNamespace(type="audio", codec_context=None, start_time=0, index=1),
        ]

    def __enter__(self) -> "_FakeContainer":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def close(self) -> None:
        pass


def test_codec_fake_audio_unsupported(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    def fake_open(*args: object, **kwargs: object) -> _FakeContainer:
        return _FakeContainer()

    monkeypatch.setattr(av, "open", fake_open)
    with pytest.raises(DecodeError) as info:
        next(D.iter_audio(FAKE_AUDIO, warn=sink.append))
    assert info.value.warning.code is WarningCode.UNSUPPORTED_CODEC
    assert "audio stream 1" in info.value.warning.detail


def test_codec_prores_decodes_on_cpu(sink: list[AssetWarning]) -> None:
    frames = _frames(PRORES, None, sink)
    assert len(frames) == 10
    for f in frames:
        assert f.pixels.shape == (120, 160, 3)
        assert f.pixels.dtype == np.uint8


# ---- row 15: a stream index that isn't in the container ----


def test_index_not_in_container(sink: list[AssetWarning]) -> None:
    with pytest.raises(DecodeError) as video:
        next(D.iter_frames(BAD_INDEX, None, warn=sink.append))
    assert video.value.warning.code is WarningCode.UNREADABLE
    assert video.value.warning.detail == "video stream 5: not in container"
    with pytest.raises(DecodeError) as audio:
        next(D.iter_audio(BAD_INDEX, warn=sink.append))
    assert audio.value.warning.code is WarningCode.UNREADABLE
    assert audio.value.warning.detail == "audio stream 7: not in container"


# ---- row 16: ruling 4: no stream, no open ----


def _missing_video(tmp_path: Path) -> AssetInfo:
    return _asset(tmp_path / "absent.mp4", None, None, ())


def test_nostream_frames_without_open(tmp_path: Path, sink: list[AssetWarning]) -> None:
    assert list(D.iter_frames(_missing_video(tmp_path), None, warn=sink.append)) == []
    assert sink == []


def test_nostream_audio_without_open(tmp_path: Path, sink: list[AssetWarning]) -> None:
    assert list(D.iter_audio(_missing_video(tmp_path), warn=sink.append)) == []
    assert sink == []


# ---- row 17: R9: argument validation ----

_BAD_ARGS: list[tuple[str, Callable[[WarningSink], Iterator[object]]]] = [
    ("frames-every-0", lambda w: D.iter_frames(CLEAN, 0, warn=w)),
    ("frames-every-neg", lambda w: D.iter_frames(CLEAN, -0.5, warn=w)),
    ("rate-0", lambda w: D.iter_audio(CLEAN, 0, warn=w)),
    ("chunk-0", lambda w: D.iter_audio(CLEAN, chunk_s=0, warn=w)),
    ("chunk-rounds-to-0", lambda w: D.iter_audio(CLEAN, chunk_s=1e-5, warn=w)),
    ("track-past-end", lambda w: D.iter_audio(CLEAN, track=1, warn=w)),
    ("track-neg", lambda w: D.iter_audio(CLEAN, track=-1, warn=w)),
    ("track-0-no-audio", lambda w: D.iter_audio(NO_AUDIO, track=0, warn=w)),
    ("frames-every-nan", lambda w: D.iter_frames(CLEAN, math.nan, warn=w)),
    ("frames-every-inf", lambda w: D.iter_frames(CLEAN, math.inf, warn=w)),
    ("rate-nan", lambda w: D.iter_audio(CLEAN, math.nan, warn=w)),  # type: ignore[arg-type]
    ("rate-inf", lambda w: D.iter_audio(CLEAN, math.inf, warn=w)),  # type: ignore[arg-type]
    ("chunk-nan", lambda w: D.iter_audio(CLEAN, chunk_s=math.nan, warn=w)),
    ("chunk-inf", lambda w: D.iter_audio(CLEAN, chunk_s=math.inf, warn=w)),
]


@pytest.mark.parametrize("make", [m for _, m in _BAD_ARGS], ids=[i for i, _ in _BAD_ARGS])
def test_args_rejected_on_first_next(
    make: Callable[[WarningSink], Iterator[object]], sink: list[AssetWarning]
) -> None:
    it = make(sink.append)  # a generator: nothing runs until next()
    with pytest.raises(ValueError):
        next(it)


@pytest.mark.parametrize("make", [m for _, m in _BAD_ARGS], ids=[i for i, _ in _BAD_ARGS])
def test_args_rejected_before_open(
    make: Callable[[WarningSink], Iterator[object]],
    monkeypatch: pytest.MonkeyPatch,
    sink: list[AssetWarning],
) -> None:
    def no_open(*args: object, **kwargs: object) -> None:
        raise AssertionError("file opened before argument validation")

    monkeypatch.setattr(av, "open", no_open)
    with pytest.raises(ValueError):
        next(make(sink.append))


# ---- row 18: pure timestamp math ----


@_PROP
@given(st.floats(-1e9, 1e9))
def test_math_half_up(x: float) -> None:
    assert (half_up(0.5), half_up(2.5), half_up(-0.5)) == (1, 3, 0)
    y = half_up(x)
    assert isinstance(y, int)
    assert y == math.floor(x + 0.5)


@_PROP
@given(
    st.integers(-(2**40), 2**40),
    st.integers(1, 1001),
    st.integers(1, 10**6),
    st.floats(-1e4, 1e4),
)
def test_math_clock_s(pts: int, num: int, den: int, start: float) -> None:
    assert clock_s(1500, Fraction(1, 1000), 0.0) == 1.5
    assert clock_s(0, Fraction(1, 1000), -0.064) == 0.064
    tb = Fraction(num, den)
    assert clock_s(pts, tb, start) == float(pts * tb) - start


@_PROP
@given(
    st.lists(st.floats(-10.0, 20.0), max_size=50),
    st.none() | st.floats(0.0, 15.0),
)
def test_math_frame_kept(ts: list[float], duration: float | None) -> None:
    last: float | None = None
    kept: list[float] = []
    for t in ts:
        ok = frame_kept(t, duration, last)
        assert ok == (t >= 0 and (duration is None or t < duration) and (last is None or t > last))
        if ok:
            kept.append(t)
            last = t
    assert all(a < b for a, b in itertools.pairwise(kept))
    assert all(t >= 0 and (duration is None or t < duration) for t in kept)


@_PROP
@given(st.floats(0.0, 1e5), st.floats(1e-3, 1e3))
def test_math_window_index(t: float, e: float) -> None:
    assert window_index(0.3, 0.1) == 3
    k = window_index(t, e)
    assert isinstance(k, int)
    assert k >= 0
    assert k * e <= t + 1e-9 * e
    assert t < (k + 1) * e


@_PROP
@given(st.integers(1, 20_000), st.integers(1, 20_000))
def test_math_upright_size(h: int, w: int) -> None:
    assert upright_size(2160, 3840) == (432, 768)
    assert upright_size(240, 320) == (240, 320)
    h2, w2 = upright_size(h, w)
    assert max(h2, w2) <= MAX_SIDE_PX
    assert min(h2, w2) >= 1
    m = max(h, w)
    if m <= MAX_SIDE_PX:
        assert (h2, w2) == (h, w)
    else:
        assert max(h2, w2) == MAX_SIDE_PX
        for side, side2 in ((h, h2), (w, w2)):
            exact = Fraction(side * MAX_SIDE_PX, m)
            assert side2 == 1 or abs(side2 - exact) <= Fraction(1, 2) + Fraction(1, 10**9)


_SR = 16_000


@pytest.mark.parametrize(
    ("t", "run_end", "expected"),
    [
        pytest.param(
            0.0,
            None,
            {"new_run": True, "start_s": 0.0, "fill": 0, "skip": 0, "keep": 1024},
            id="first-frame",
        ),
        pytest.param(
            0.25, 0.25, {"new_run": False, "fill": 0, "skip": 0, "keep": 1024}, id="contiguous"
        ),
        pytest.param(0.25 + 0.5 / _SR, 0.25, {"fill": 0, "skip": 0}, id="sub-period-gap"),
        pytest.param(0.375, 0.25, {"fill": 2000}, id="gap-filled"),
        pytest.param(0.75, 0.25, {"new_run": False, "fill": 8000}, id="gap-exactly-fill-limit"),
        pytest.param(
            0.8,
            0.25,
            {"new_run": True, "start_s": pytest.approx(0.8), "fill": 0},
            id="gap-over-limit-new-run",
        ),
        pytest.param(0.24, 0.25, {"skip": 160, "keep": 864}, id="overlap-dropped"),
        pytest.param(
            None,
            0.25,
            {"new_run": False, "fill": 0, "skip": 0, "keep": 1024},
            id="no-pts-continues",
        ),
        pytest.param(None, None, {"keep": 0, "fill": 0}, id="no-pts-no-run"),
        pytest.param(
            -0.01,
            None,
            {"new_run": True, "skip": 160, "start_s": pytest.approx(0.0), "keep": 864},
            id="negative-start-trimmed",
        ),
    ],
)
def test_math_place_audio_cases(
    t: float | None, run_end: float | None, expected: dict[str, object]
) -> None:
    p = place_audio(t, 1024, sample_rate=_SR, run_end_s=run_end, duration_s=5.0)
    assert isinstance(p, Placement)
    assert {k: getattr(p, k) for k in expected} == expected


@_PROP
@given(
    st.none() | st.floats(-2.0, 10.0),
    st.integers(0, 4096),
    st.sampled_from([8000, 16_000, 44_100, 48_000]),
    st.none() | st.floats(0.0, 10.0),
    st.none() | st.floats(0.001, 12.0),
)
def test_math_place_audio_property(
    t: float | None, n: int, sr: int, run_end: float | None, duration: float | None
) -> None:
    p = place_audio(t, n, sample_rate=sr, run_end_s=run_end, duration_s=duration)
    assert min(p.fill, p.skip, p.keep) >= 0
    assert p.skip + p.keep <= n
    assert p.fill <= half_up(AUDIO_GAP_FILL_S * sr)
    if p.new_run:
        assert p.fill == 0


def _ones(n: int) -> NDArray[np.float32]:
    return np.ones(n, np.float32)


def _zeros(n: int) -> NDArray[np.float32]:
    return np.zeros(n, np.float32)


_Piece = tuple[bool, float, NDArray[np.float32]]


@pytest.mark.parametrize(
    ("pieces", "expected"),
    [
        pytest.param(
            [
                (True, 0.0, _ones(900)),
                (False, 900 / _SR, np.concatenate([_zeros(300), _ones(100)])),
                (True, 2.0, _ones(50)),
            ],
            [
                (0.0, np.concatenate([_ones(900), _zeros(100)])),
                (0.0625, np.concatenate([_zeros(200), _ones(100)])),
                (2.0, _ones(50)),
            ],
            id="fill-crosses-boundary",
        ),
        pytest.param(
            [(True, 0.0, _ones(100)), (True, 2.0, _zeros(0)), (False, 2.0, _ones(50))],
            [(0.0, _ones(100)), (2.0, _ones(50))],
            id="empty-new-run",
        ),
    ],
)
def test_math_chunk_runs_cases(
    pieces: list[_Piece], expected: list[tuple[float, NDArray[np.float32]]]
) -> None:
    chunks = list(chunk_runs(pieces, chunk_n=1000, sample_rate=_SR))
    assert len(chunks) == len(expected)
    for chunk, (start_s, samples) in zip(chunks, expected, strict=True):
        assert chunk.start_s == pytest.approx(start_s)
        assert chunk.sample_rate == _SR
        assert np.array_equal(chunk.samples, samples)


@_PROP
@given(
    st.lists(
        st.tuples(st.booleans(), st.floats(0.0, 1000.0), st.integers(0, 120)),
        min_size=1,
        max_size=10,
    ),
    st.integers(1, 50),
    st.sampled_from([8000, 16_000]),
)
def test_math_chunk_runs_property(
    spec: list[tuple[bool, float, int]], chunk_n: int, sr: int
) -> None:
    pieces: list[_Piece] = []
    runs: list[tuple[float, list[NDArray[np.float32]]]] = []
    counter = 0
    for i, (new_run, start, n) in enumerate(spec):
        samples = (np.arange(counter, counter + n) / 2048).astype(np.float32)  # unique, in [0, 1)
        counter += n
        if i == 0 or new_run:
            runs.append((start, [samples]))
            pieces.append((True, start, samples))
        else:
            run_start, parts = runs[-1]
            parts.append(samples)
            done = sum(p.size for p in parts[:-1])
            pieces.append((False, run_start + done / sr, samples))
    chunks = list(chunk_runs(pieces, chunk_n=chunk_n, sample_rate=sr))
    assert all(c.samples.size >= 1 for c in chunks)
    assert all(c.sample_rate == sr for c in chunks)
    pos = 0
    for run_start, parts in runs:
        total = np.concatenate(parts)
        n_chunks = math.ceil(total.size / chunk_n)
        mine = chunks[pos : pos + n_chunks]
        pos += n_chunks
        assert len(mine) == n_chunks
        if not n_chunks:
            continue
        assert np.array_equal(np.concatenate([c.samples for c in mine]), total)
        assert all(c.samples.size == chunk_n for c in mine[:-1])
        for j, c in enumerate(mine):
            assert c.start_s == pytest.approx(run_start + j * chunk_n / sr, abs=1e-9)
    assert pos == len(chunks)


_Event = float | Literal["fail"]
_Run = tuple[float, float | None]


def _drive(events: tuple[_Event, ...], duration_s: float | None) -> list[_Run]:
    """Feed good video items (start == end == t) and failures, then EOF; return the raw runs."""
    state = GapState()
    runs: list[_Run] = []
    for ev in events:
        if ev == "fail":
            state = gap_on_fail(state)
        else:
            state, run = gap_on_good(state, ev, ev)
            if run is not None:
                runs.append(run)
    eof = gap_on_eof(state, duration_s)
    if eof is not None:
        runs.append(eof)
    return runs


def test_math_gap_state_machine() -> None:
    # A no-PTS frame calls nothing: it neither opens nor closes a run.
    events: tuple[_Event, ...] = (0.0, 0.04, "fail", "fail", 0.2, "fail")
    assert _drive(events, 1.0) == [(0.04, 0.2), (0.2, 1.0)]
    runs = _drive(events, None)
    assert runs == [(0.04, 0.2), (0.2, None)]
    clamped = clamp_run(runs[-1], None)
    assert clamped is not None
    assert clamped == (0.2, None)
    warning = gap_warning("video", 0, clamped, 1)
    assert warning is not None
    assert warning.detail.endswith("-end s")
    assert warning.detail == "video stream 0: undecodable 0.20-end s"


def test_math_gap_flush_never_closes_run() -> None:
    # Owner ruling (#6, amends R10): end-of-stream flush frames are yielded but never close
    # an open run; it closes at EOF. Sequence mirrors truncated.mp4.
    state = GapState()
    for t in (0.0, 3.12):
        state, run = gap_on_good(state, t, t)
        assert run is None
    state = gap_on_fail(state)
    state = gap_on_flush(state, 3.16)
    state = gap_on_flush(state, 3.24)
    assert state.open_from_s == 3.24  # still open: the flush closed nothing
    eof = gap_on_eof(state, 6.0)
    assert eof is not None
    assert eof == (3.24, 6.0)
    clamped = clamp_run(eof, 6.0)
    assert clamped is not None
    warning = gap_warning("video", 0, clamped, 0)
    assert warning is not None
    assert warning.detail == "video stream 0: undecodable 3.24-6.00 s"
    # With no open run, a flush item acts like gap_on_good.
    assert gap_on_flush(GapState(last_good_end_s=1.0), 2.0) == GapState(
        last_good_end_s=2.0, open_from_s=None
    )


_gap_event = st.one_of(
    st.just("fail"),
    st.just("nopts"),
    st.tuples(st.floats(0.001, 2.0), st.floats(0.0, 1.0)),  # (gap since last start, length)
)


@_PROP
@given(
    st.lists(_gap_event, max_size=40),
    st.floats(-1.0, 1.0),
    st.none() | st.floats(0.0, 30.0),
)
def test_math_gap_property(
    events: list[str | tuple[float, float]], t0: float, duration: float | None
) -> None:
    state = GapState()
    runs: list[_Run] = []
    t = t0
    streaks = 0
    failing = False
    for ev in events:
        if ev == "nopts":
            continue  # neutral: neither opens nor closes a run
        if isinstance(ev, str):
            state = gap_on_fail(state)
            failing = True
        else:
            delta, length = ev
            t += delta
            state, run = gap_on_good(state, t, t + length)
            if failing:
                streaks += 1
                failing = False
                assert run is not None
            else:
                assert run is None
            if run is not None:
                runs.append(run)
    assert len(runs) == streaks
    eof = gap_on_eof(state, duration)
    if state.open_from_s is not None:
        assert eof == (state.open_from_s, duration)
    elif eof is not None:
        assert duration is not None
        assert eof == (state.last_good_end_s, duration)
        assert state.last_good_end_s < duration - EARLY_EOF_S
    if eof is not None:
        runs.append(eof)
    clamped = [c for r in runs if (c := clamp_run(r, duration)) is not None]
    for a, b in clamped:
        assert a >= 0.0
        assert b is None or a < b
    for (_, b1), (a2, _) in itertools.pairwise(clamped):
        assert b1 is not None
        assert b1 <= a2


@pytest.mark.parametrize(
    ("events", "duration", "runs", "details"),
    [
        pytest.param(
            (3.24,),
            6.0,
            [(3.24, 6.0)],
            ["video stream 0: undecodable 3.24-6.00 s"],
            id="early-eof",
        ),
        pytest.param((5.5,), 6.0, [], [], id="within-early-eof-s"),
        pytest.param((5.0,), 6.0, [], [], id="exactly-early-eof-s"),
        pytest.param((3.24,), None, [], [], id="no-duration"),
        pytest.param(
            (0.0, "fail", 1.0, 3.24),
            6.0,
            [(0.0, 1.0), (3.24, 6.0)],
            ["video stream 0: undecodable 0.00-1.00 s", "video stream 0: undecodable 3.24-6.00 s"],
            id="closed-run-then-early-eof",
        ),
    ],
)
def test_math_early_eof(
    events: tuple[_Event, ...],
    duration: float | None,
    runs: list[tuple[float, float | None]],
    details: list[str],
) -> None:
    got = _drive(events, duration)
    assert got == runs
    warnings: list[AssetWarning] = []
    for run in got:
        clamped = clamp_run(run, duration)
        assert clamped is not None
        w = gap_warning("video", 0, clamped, len(warnings))
        assert w is not None
        assert w.code is WarningCode.PARTIAL_DECODE
        warnings.append(w)
    assert [w.detail for w in warnings] == details


@pytest.mark.parametrize(
    ("run", "duration", "expected"),
    [
        ((-0.5, 1.0), 6.0, (0.0, 1.0)),
        ((1.0, 7.0), 6.0, (1.0, 6.0)),
        ((2.0, 1.5), 6.0, None),
        ((6.0, 6.0), 6.0, None),
        ((1.0, None), None, (1.0, None)),
    ],
    ids=["neg-start", "past-duration", "reversed", "empty", "open-end"],
)
def test_math_clamp_run(
    run: tuple[float, float | None],
    duration: float | None,
    expected: tuple[float, float | None] | None,
) -> None:
    assert clamp_run(run, duration) == expected


def test_math_gap_cap() -> None:
    events: list[_Event] = [0.0]
    for i in range(1, 25):
        events += ["fail", float(i)]
    raw = _drive(tuple(events), 30.0)
    assert len(raw) == 25
    assert raw[-1] == (24.0, 30.0)  # the 25th run is the early-EOF run
    raw.insert(3, (31.0, 32.0))  # clamp_run rejects it: counts toward neither
    results: list[AssetWarning | None] = []
    for run in raw:
        clamped = clamp_run(run, 30.0)
        if clamped is None:
            continue
        sent = sum(r is not None for r in results)
        results.append(gap_warning("video", 0, clamped, sent))
    assert len(results) == 25
    sent_ok = [r for r in results if r is not None]
    assert len(sent_ok) == MAX_GAP_WARNINGS == 20
    assert all(r is not None for r in results[:20])
    assert results[20] is None
    assert all(r is None for r in results[20:])
    assert all(r.code is WarningCode.PARTIAL_DECODE for r in sent_ok)
    assert sent_ok[0].detail == "video stream 0: undecodable 0.00-1.00 s"
    summary = gap_summary(len(results))
    assert summary is not None
    assert summary.code is WarningCode.PARTIAL_DECODE
    assert summary.detail == "5 more undecodable runs not listed"
    assert gap_summary(20) is None


# ---- row 19: R10: buffering bound ----


@pytest.mark.slow
def test_long_tracemalloc_peak(sink: list[AssetWarning]) -> None:
    count = 0
    last_t = -1.0
    tracemalloc.start()
    try:
        for frame in D.iter_frames(LONG_3H, None, warn=sink.append):
            count += 1
            last_t = frame.t_s
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert count == 10_800
    assert abs(last_t - 10_799) <= 1
    assert peak < 16 * 2**20


_RSS_SCRIPT = """\
import resource
import sys
from pathlib import Path

import av  # noqa: F401

from tapesift.media.decode import PyAVDecoder
from tapesift.media.types import AssetInfo, AudioStreamInfo, VideoInfo


def peak():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024


fixtures = Path(sys.argv[1])
ident = "tsid1:" + "0" * 64
clean = AssetInfo(
    ident, fixtures / "clean.mp4", 5.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0),
    (AudioStreamInfo(1, "aac", "und", True),), (),
)
long_3h = AssetInfo(
    ident, fixtures / "long_3h.mp4", 10800.0, VideoInfo(0, "h264", 64, 36, 1.0, False, 0),
    (), (),
)
decoder = PyAVDecoder()
sink = []
next(decoder.iter_frames(clean, None, warn=sink.append))
baseline = peak()
for _frame in decoder.iter_frames(long_3h, None, warn=sink.append):
    pass
print(f"baseline={baseline} peak={peak()}")
"""


@pytest.mark.slow
def test_long_rss_peak() -> None:
    out = subprocess.run(
        [sys.executable, "-c", _RSS_SCRIPT, str(FIXTURES)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    m = re.fullmatch(r"baseline=(\d+) peak=(\d+)", out.stdout.strip())
    assert m is not None
    baseline, peak = int(m.group(1)), int(m.group(2))
    assert peak <= baseline + 100 * 2**20


# ---- row 24: review round 1 (2026-10-17): security open, resampler errors, boundary tests ----


class _Spy:
    """Wraps a real container: overrides start_time, records close."""

    def __init__(self, real: Any, start_time: int | None = None) -> None:
        self.real = real
        self.closed = False
        self.start_time = real.start_time if start_time is None else start_time

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)

    def __enter__(self) -> "_Spy":
        return self

    def __exit__(self, *exc: object) -> None:
        self.closed = True
        self.real.close()


def _patch_open(monkeypatch: pytest.MonkeyPatch, start_time: int | None = None) -> list[_Spy]:
    real_open = av.open
    made: list[_Spy] = []

    def wrap(*args: Any, **kwargs: Any) -> _Spy:
        made.append(_Spy(real_open(*args, **kwargs), start_time))
        return made[-1]

    monkeypatch.setattr(av, "open", wrap)
    return made


def test_review_open_name_is_not_a_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    shutil.copyfile(CLEAN.path, tmp_path / "concat:x")
    monkeypatch.chdir(tmp_path)  # a relative path: av.open("concat:x") would pick the protocol
    asset = _asset(Path("concat:x"), CLEAN.duration_s, CLEAN.video, CLEAN.audio)
    frames = _frames(asset, None, sink)
    ref = _frames(CLEAN, None, [])
    assert len(frames) == len(ref) == 125
    assert np.array_equal(frames[0].pixels, ref[0].pixels)
    assert sink == []


def test_review_open_playlist_cannot_reach_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    def no_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("socket connect")

    monkeypatch.setattr(socket.socket, "connect", no_connect)  # the stdlib sockets
    hits: list[int] = []
    with socket.socket() as srv:  # FFmpeg's C sockets: a local listener sees any attempt
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        srv.settimeout(0.2)
        port = srv.getsockname()[1]

        def serve() -> None:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            hits.append(1)
            conn.close()

        t = threading.Thread(target=serve)
        t.start()
        path = tmp_path / "evil.m3u8"
        path.write_text(
            f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:{port}/x.ts\n"
            "#EXT-X-ENDLIST\n"
        )
        evil = _asset(path, 1.0, VideoInfo(0, "h264", 320, 240, 25.0, False, 0))
        with pytest.raises(DecodeError) as info:
            next(D.iter_frames(evil, None, warn=sink.append))
        t.join()
    assert info.value.warning.code is WarningCode.UNREADABLE
    assert hits == []


def test_review_resampler_value_error_is_a_gap(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    real = av.AudioResampler

    class Flaky:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.inner = real(*args, **kwargs)
            self.calls = 0

        def resample(self, frame: Any) -> Any:
            if frame is not None:
                self.calls += 1
                if self.calls == 3:
                    raise ValueError("Frame does not match AudioResampler setup.")
            return self.inner.resample(frame)

    monkeypatch.setattr(av, "AudioResampler", Flaky)
    chunks = list(D.iter_audio(CLEAN, chunk_s=1.0, warn=sink.append))
    assert chunks
    assert len(_partials(sink)) == 1


class _Proxy:
    """A packet whose decode raises (after really decoding, to keep the decoder in step)."""

    def __init__(self, packet: Any, fail: bool) -> None:
        self.packet = packet
        self.fail = fail
        self.size = packet.size

    def decode(self) -> Any:
        frames = self.packet.decode()
        if self.fail:
            raise InvalidDataError(1, "injected")
        return frames


def test_review_warning_cap_and_summary_via_iter_frames(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    real_open = av.open

    class Failing(_Spy):
        def demux(self, *streams: Any) -> Iterator[_Proxy]:
            for i, pkt in enumerate(self.real.demux(*streams)):
                yield _Proxy(pkt, pkt.size > 0 and i % 5 == 4)

    monkeypatch.setattr(av, "open", lambda *a, **k: Failing(real_open(*a, **k)))
    _frames(CLEAN, None, sink)
    partial = _partials(sink)
    assert len(partial) == MAX_GAP_WARNINGS + 1
    assert all("undecodable" in w.detail for w in partial[:-1])
    assert partial[-1].detail == "5 more undecodable runs not listed"


class _FakeAudio:
    """A container whose audio stream 1 yields the given AudioFrames, one per packet."""

    start_time = 0
    duration = 1_000_000

    def __init__(self, frames: list[Any]) -> None:
        self.frames = frames
        self.streams = [
            SimpleNamespace(type="video", index=0, codec_context=object()),
            SimpleNamespace(type="audio", index=1, codec_context=object()),
        ]
        self.closed = False

    def demux(self, *streams: object) -> Iterator[SimpleNamespace]:
        for f in self.frames:
            yield SimpleNamespace(size=1, decode=lambda f=f: [f])

    def __enter__(self) -> "_FakeAudio":
        return self

    def __exit__(self, *exc: object) -> None:
        self.closed = True

    def close(self) -> None:
        self.closed = True


def _aframe(start_sample: int, value: float, n: int = 1600) -> Any:
    f = av.AudioFrame.from_ndarray(np.full((1, n), value, np.float32), format="flt", layout="mono")
    f.sample_rate = 16_000
    f.pts = start_sample
    f.time_base = Fraction(1, 16_000)
    return f


def _fake_audio(
    monkeypatch: pytest.MonkeyPatch, frames: list[Any], duration_s: float = 1.0
) -> tuple[AssetInfo, _FakeAudio]:
    fake = _FakeAudio(frames)
    monkeypatch.setattr(av, "open", lambda *a, **k: fake)
    return _asset(CLEAN.path, duration_s, None, _AAC), fake


def test_review_audio_gap_fill(monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]) -> None:
    asset, _ = _fake_audio(monkeypatch, [_aframe(0, 0.5), _aframe(3200, 0.25)])  # 0.1 s gap
    chunks = list(D.iter_audio(asset, chunk_s=1.0, warn=sink.append))
    assert len(chunks) == 1
    assert chunks[0].start_s == 0.0
    s = chunks[0].samples
    assert s.size == 4800
    assert np.allclose(s[:1600], 0.5, atol=1e-3)
    assert np.all(s[1600:3200] == 0)
    assert np.allclose(s[3200:], 0.25, atol=1e-3)


def test_review_audio_overlap_dropped(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    asset, _ = _fake_audio(monkeypatch, [_aframe(0, 0.5), _aframe(1440, 0.25)])  # 160 overlap
    chunks = list(D.iter_audio(asset, chunk_s=1.0, warn=sink.append))
    assert len(chunks) == 1
    s = chunks[0].samples
    assert s.size == 1600 + 1440
    assert np.allclose(s[:1600], 0.5, atol=1e-3)
    assert np.allclose(s[1600:], 0.25, atol=1e-3)


def test_review_audio_negative_start_trimmed(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    asset, _ = _fake_audio(monkeypatch, [_aframe(-160, 0.5)])  # starts at -0.01 s
    chunks = list(D.iter_audio(asset, chunk_s=1.0, warn=sink.append))
    assert len(chunks) == 1
    assert chunks[0].start_s == pytest.approx(0.0, abs=1e-9)
    assert chunks[0].samples.size == 1440


def test_review_rotation_then_downscale(sink: list[AssetWarning]) -> None:
    video = VideoInfo(0, "h264", 3840, 2160, 5.0, False, 90)
    asset = _asset(UHD_4K.path, 1.0, video)
    frames = _frames(asset, None, sink)
    assert len(frames) == 5
    assert all(f.pixels.shape == (768, 432, 3) for f in frames)  # portrait: rotated, then resized


def test_review_rotation_180_pixels() -> None:
    video = VideoInfo(0, "h264", 320, 240, 25.0, False, 180)
    rotated = _first_frame(_asset(CLEAN.path, 5.0, video)).pixels
    assert np.array_equal(rotated, np.rot90(_first_frame(CLEAN).pixels, 2))


def test_review_area_downscale_bar_colours() -> None:
    p = _first_frame(UHD_4K).pixels.astype(int)
    assert np.abs(p[100, 120] - 191).max() <= 6  # 75% grey bar
    assert np.abs(p[100, 240] - np.array([189, 202, 7])).max() <= 8  # yellow bar


def test_review_clip_full_scale_wav(tmp_path: Path, sink: list[AssetWarning]) -> None:
    path = tmp_path / "loud.wav"
    square = np.where((np.arange(8000) // 40) % 2 == 0, 32767, -32768).astype("<i2")
    with path.open("wb") as fh, wave.open(fh, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(square.tobytes())
    asset = _asset(path, 1.0, None, (AudioStreamInfo(0, "pcm_s16le", None, True),))
    samples = _joined(list(D.iter_audio(asset, warn=sink.append)))
    assert samples.size > 0
    assert float(samples.max()) == 1.0 or float(samples.min()) == -1.0  # it does reach full scale
    assert float(samples.min()) >= -1.0
    assert float(samples.max()) <= 1.0


def test_review_truncated_audio_gap_starts_at_3_20(sink: list[AssetWarning]) -> None:
    list(D.iter_audio(TRUNCATED, warn=sink.append))
    assert [w.detail for w in _partials(sink)] == ["audio stream 1: undecodable 3.20-6.00 s"]


def test_review_truncated_sampled_frames_one_warning(sink: list[AssetWarning]) -> None:
    assert _frames(TRUNCATED, 1.0, sink)
    assert len(_partials(sink)) == 1


def test_review_duration_cuts_frames_and_audio(sink: list[AssetWarning]) -> None:
    short = _asset(CLEAN.path, 2.0, CLEAN.video, CLEAN.audio)
    frames = _frames(short, None, sink)
    assert len(frames) == 50
    assert frames[-1].t_s < 2.0
    audio = _joined(list(D.iter_audio(short, chunk_s=1.0, warn=sink.append)))
    assert audio.size <= 32_000


def test_review_container_start_shifts_t_s(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    _patch_open(monkeypatch, start_time=-1_000_000)  # container starts at -1 s
    frames = _frames(CLEAN, None, sink)
    assert frames[0].t_s == pytest.approx(1.0, abs=1e-6)
    assert len(frames) == 100  # t_s = pts + 1.0 < duration 5.0
    assert all(f.t_s < 5.0 for f in frames)


def test_review_early_close_frames(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    made = _patch_open(monkeypatch)
    it = cast("Generator[Frame]", D.iter_frames(TRUNCATED, None, warn=sink.append))
    for _ in zip(range(2), it, strict=False):
        pass
    it.close()
    assert made[0].closed
    assert sink == []


def test_review_early_close_audio(
    monkeypatch: pytest.MonkeyPatch, sink: list[AssetWarning]
) -> None:
    made = _patch_open(monkeypatch)
    it = cast("Generator[AudioChunk]", D.iter_audio(TRUNCATED, chunk_s=1.0, warn=sink.append))
    next(it)
    it.close()
    assert made[0].closed
    assert sink == []


@pytest.mark.parametrize("kind", ["frames", "audio"])
def test_review_zero_byte_file(tmp_path: Path, kind: str, sink: list[AssetWarning]) -> None:
    path = tmp_path / "empty.mp4"
    path.write_bytes(b"")
    asset = _asset(path, 5.0, CLEAN.video, CLEAN.audio)
    it = (
        D.iter_frames(asset, None, warn=sink.append)
        if kind == "frames"
        else D.iter_audio(asset, warn=sink.append)
    )
    with pytest.raises(DecodeError) as info:
        next(it)
    assert info.value.warning.code is WarningCode.UNREADABLE


def test_review_audio_memory_bound(tmp_path: Path, sink: list[AssetWarning]) -> None:
    rate, secs = 16_000, 600
    t = np.arange(rate * 60) / rate
    minute = np.round(np.sin(2 * np.pi * 440 * t) * 16000).astype("<i2").tobytes()
    path = tmp_path / "ten_minutes.wav"
    with path.open("wb") as fh, wave.open(fh, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for _ in range(secs // 60):
            w.writeframes(minute)
    asset = _asset(path, float(secs), None, (AudioStreamInfo(0, "pcm_s16le", None, True),))
    total = 0
    tracemalloc.start()
    try:
        for chunk in D.iter_audio(asset, rate, chunk_s=60, warn=sink.append):
            total += chunk.samples.size
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert total == rate * secs
    assert peak < 8 * 2**20
