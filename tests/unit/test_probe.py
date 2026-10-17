from __future__ import annotations

import json
import logging
import shutil
import struct
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import TYPE_CHECKING, Any

import av
import av.error
import numpy as np
import pytest
from av.audio.frame import AudioFrame
from av.stream import Disposition
from av.video.frame import VideoFrame
from hypothesis import given
from hypothesis import strategies as st

from tapesift.media.probe import (
    PROBE_TIMEOUT_S,
    _rotation_from_matrix,
    _select_video,
    _stream_end_s,
    _stream_start_s,
    probe,
)
from tapesift.media.types import AssetInfo, ProbeError
from tapesift.warning_codes import AssetWarning, WarningCode

if TYPE_CHECKING:
    from av.container import InputContainer
    from av.packet import PktSideDataT

FIXTURES = Path(__file__).parents[1] / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = MANIFEST["fixtures"]
BY_NAME = {e["name"]: e for e in ENTRIES}

W = WarningCode
PROBE_CODES = frozenset(
    {
        W.VFR_DETECTED,
        W.ROTATED,
        W.START_OFFSET,
        W.AV_LENGTH_MISMATCH,
        W.NO_AUDIO,
        W.MULTI_AUDIO,
        W.UNSUPPORTED_CODEC,
        W.INTERLACED,
        W.HDR_CONVERTED,
        W.SHORT_CLIP,
        W.DOWNSCALED,
    }
)
OWNED_ELSEWHERE = frozenset({W.PARTIAL_DECODE, W.CROPPED, W.LOW_SPEECH, W.MEDIA_TEXT, W.DUPLICATE})

# Fixtures with no audio stream. The NO_AUDIO rule (`video is not None and not audio`) fires
# on every one of them, but the manifest lists only the case each fixture was built for, so
# test_manifest_codes expects NO_AUDIO on top of the manifest codes here (owner, card answered
# 2026-10-17; docs/specs/5-probe.md amended).
VIDEO_ONLY = frozenset(
    {
        "vfr.mp4",
        "rotated_270.mp4",
        "no_audio.mp4",
        "prores.mov",
        "unknown_codec.mov",
        "interlaced.mp4",
        "letterbox.mp4",
        "pillarbox.mp4",
        "hdr10.mkv",
        "long_3h.mp4",
        "uhd_4k.mp4",
        "burned_text.mp4",
    }
)

# Extra per-fixture expectations from the spec's test_manifest_codes table.
VIDEO_EXPECT: dict[str, dict[str, object]] = {
    "vfr.mp4": {"vfr": True},
    "rotated.mp4": {"rotation": 90},
    "rotated_270.mp4": {"rotation": 270, "w": 320, "h": 240},  # stored size, not displayed
    "unknown_codec.mov": {"codec": "unknown"},
}

_MS = Fraction(1, 1000)
_FPS25 = Fraction(25)
_NO_FLAGS = Disposition(0)
_Q30 = 1 << 30


def _pattern(n: int) -> bytes:
    k = n // 251 + 1
    return (bytes(range(251)) * k)[:n]


# --- stand-ins for PyAV streams and containers (they implement every Protocol property) ---


@dataclass
class _FakeCodec:
    name: str = "h264"
    width: int = 320
    height: int = 240
    field_order: int = 1  # progressive: no INTERLACED
    color_trc: int = 1  # BT.709: no HDR_CONVERTED, and probe never needs to open the codec
    coded_side_data: dict[PktSideDataT, bytes] = field(default_factory=dict)
    open_error: Exception | None = None  # raised by open() when set
    trc_after_open: int | None = None  # color_trc after a successful open(), when set
    open_calls: list[bool] = field(default_factory=list)  # the `strict` of each open() call

    def open(self, strict: bool = True) -> None:
        self.open_calls.append(strict)
        if self.open_error is not None:
            raise self.open_error
        if self.trc_after_open is not None:
            self.color_trc = self.trc_after_open


@dataclass
class _FakeStream:
    index: int
    codec_context: _FakeCodec | None = field(default_factory=_FakeCodec)
    start_time: int | None = 0
    duration: int | None = 5000
    time_base: Fraction = _MS
    disposition: Disposition = _NO_FLAGS
    average_rate: Fraction = _FPS25
    base_rate: Fraction = _FPS25
    language: str | None = None


def _audio(
    index: int, start_time: int = 0, duration: int = 5000, *, no_decoder: bool = False
) -> _FakeStream:
    codec = None if no_decoder else _FakeCodec(name="aac", width=0, height=0)
    return _FakeStream(
        index,
        codec_context=codec,
        start_time=start_time,
        duration=duration,
        disposition=Disposition.default,
        language="eng",
    )


class _FakeContainer:
    def __init__(
        self,
        video: list[_FakeStream],
        audio: list[_FakeStream],
        *,
        start_time: int | None = None,
        duration: int | None = 5_000_000,
    ) -> None:
        self.streams = SimpleNamespace(video=video, audio=audio)
        self.start_time = start_time
        self.duration = duration
        self.closes = 0

    def __enter__(self) -> _FakeContainer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.closes += 1


def _probe_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, container: _FakeContainer
) -> AssetInfo:
    path = tmp_path / "standin.mp4"
    path.write_bytes(_pattern(4096))  # a real file, so asset_id still runs
    monkeypatch.setattr("tapesift.media.probe.av.open", lambda *_a, **_k: container)
    return probe(path)


class _ContainerSpy:
    """Wraps a real container, delegates attribute reads, and counts __exit__ calls."""

    def __init__(self, real: InputContainer) -> None:
        self._real = real
        self.exits = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)

    def __enter__(self) -> _ContainerSpy:
        self._real.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.exits += 1
        self._real.__exit__(exc_type, exc, tb)


@dataclass
class _OpenSpy:
    containers: list[_ContainerSpy] = field(default_factory=list)
    timeouts: list[object] = field(default_factory=list)


def _spy_on_open(monkeypatch: pytest.MonkeyPatch) -> _OpenSpy:
    real_open = av.open
    record = _OpenSpy()

    def fake_open(file: str, *_args: object, timeout: object = None) -> _ContainerSpy:
        record.timeouts.append(timeout)
        spy = _ContainerSpy(real_open(file))
        record.containers.append(spy)
        return spy

    monkeypatch.setattr("tapesift.media.probe.av.open", fake_open)
    return record


# --- fixtures from the manifest ---


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["name"] for e in ENTRIES])
def test_manifest_codes(entry: dict[str, Any]) -> None:
    name = str(entry["name"])
    codes = [W(c) for c in entry["warning_codes"]]
    path = FIXTURES / name
    if W.UNREADABLE in codes:
        with pytest.raises(ProbeError) as raised:
            probe(path)
        assert raised.value.warning.code == W.UNREADABLE
        return
    info = probe(path)
    got = sorted(w.code for w in info.warnings)
    expected = set(codes) & PROBE_CODES
    if name in VIDEO_ONLY:
        expected.add(W.NO_AUDIO)
    # multi_audio.mkv: under PyAV 19 the container start_time and every stream start are 0
    # (the spec's 0.064 s is not observed), so it gets no START_OFFSET either way.
    assert got == sorted(expected)  # a list: a doubled code fails
    assert (not info.audio) == (name in VIDEO_ONLY)
    if info.video is not None:
        assert info.video.vfr == (W.VFR_DETECTED in got)  # vfr is exactly the VFR condition
        assert (W.ROTATED in got) == (info.video.rotation != 0)
    for attr, value in VIDEO_EXPECT.get(name, {}).items():
        assert getattr(info.video, attr) == value
    if name == "clean_copy.mp4":
        assert info.id == probe(FIXTURES / "clean.mp4").id


DETAIL_CASES = [
    (
        "vfr.mp4",
        W.VFR_DETECTED,
        "video stream 0: average 16.85 fps vs nominal 30.00 fps; times from PTS",
    ),
    ("rotated.mp4", W.ROTATED, "video stream 0: display matrix rotation 90 deg"),
    ("rotated_270.mp4", W.ROTATED, "video stream 0: display matrix rotation 270 deg"),
    ("start_offset.mp4", W.START_OFFSET, "video stream 0 starts at 1.52 s"),
    (
        "av_mismatch.mp4",
        W.AV_LENGTH_MISMATCH,
        "video stream 0 ends at 3.00 s, audio stream 1 ends at 6.00 s",
    ),
    ("no_audio.mp4", W.NO_AUDIO, "no audio stream; ASR skipped"),
    ("multi_audio.mkv", W.MULTI_AUDIO, "2 audio streams; default is stream 1"),
    ("interlaced.mp4", W.INTERLACED, "video stream 0: field order tt; not deinterlaced"),
    (
        "hdr10.mkv",
        W.HDR_CONVERTED,
        "video stream 0: PQ transfer; decoded to 8-bit, not tone-mapped",
    ),
    ("short_clip.mp4", W.SHORT_CLIP, "duration 0.40 s"),
    (
        "uhd_4k.mp4",
        W.DOWNSCALED,
        "video stream 0: 3840x2160 downscaled to 768 px long side",
    ),
    ("unknown_codec.mov", W.UNSUPPORTED_CODEC, "stream 0 codec unknown: no decoder"),
    ("prores.mov", W.UNSUPPORTED_CODEC, "stream 0 codec prores: no NVDEC, CPU decode"),
]


@pytest.mark.parametrize(
    ("name", "code", "detail"),
    DETAIL_CASES,
    ids=[case[0] for case in DETAIL_CASES],
)
def test_fixture_detail(name: str, code: WarningCode, detail: str) -> None:
    assert AssetWarning(code, detail) in probe(FIXTURES / name).warnings


@pytest.mark.parametrize(
    ("name", "detail"),
    [
        ("not_media.txt", "InvalidDataError: Invalid data found when processing input"),
        ("missing.mp4", "FileNotFoundError: No such file or directory"),
    ],
    ids=["not_media", "missing"],
)
def test_unreadable_detail(name: str, detail: str) -> None:
    with pytest.raises(ProbeError) as raised:
        probe(FIXTURES / name)
    assert raised.value.warning == AssetWarning(W.UNREADABLE, detail)


def _standin(case: str) -> tuple[list[_FakeStream], list[_FakeStream]]:
    if case == "offset_join":
        return [_FakeStream(0, start_time=1000, duration=4000)], [
            _audio(1, start_time=-400, duration=4400)
        ]
    if case == "audio_no_decoder":
        return [_FakeStream(0)], [_audio(1, no_decoder=True)]
    if case == "no_streams":
        return [], []
    assert case == "cover_art_only"
    art = _FakeStream(
        0, codec_context=_FakeCodec(name="mjpeg"), disposition=Disposition.attached_pic
    )
    return [art], []


@pytest.mark.parametrize(
    ("case", "code", "detail"),
    [
        (
            "offset_join",
            W.START_OFFSET,
            "video stream 0 starts at 1.00 s; audio stream 1 starts at -0.40 s",
        ),
        ("audio_no_decoder", W.UNSUPPORTED_CODEC, "stream 1 codec unknown: no decoder"),
        ("no_streams", W.UNREADABLE, "no audio or video stream"),
        ("cover_art_only", W.UNREADABLE, "no audio or video stream"),
    ],
    ids=["offset_join", "audio_no_decoder", "no_streams", "cover_art_only"],
)
def test_standin_detail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str, code: WarningCode, detail: str
) -> None:
    video, audio = _standin(case)
    container = _FakeContainer(video, audio)
    if code == W.UNREADABLE:
        with pytest.raises(ProbeError) as raised:
            _probe_fake(monkeypatch, tmp_path, container)
        assert raised.value.warning == AssetWarning(code, detail)
    else:
        assert AssetWarning(code, detail) in _probe_fake(monkeypatch, tmp_path, container).warnings


def test_codec_open_failure_is_unknown_transfer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    error = av.error.InvalidDataError(-1094995529, "Invalid data found when processing input")
    codec = _FakeCodec(color_trc=2, open_error=error)  # 2: unspecified, so probe opens it
    container = _FakeContainer([_FakeStream(0, codec_context=codec)], [_audio(1)])
    info = _probe_fake(monkeypatch, tmp_path, container)  # no ProbeError
    assert info.video is not None
    assert W.HDR_CONVERTED not in {w.code for w in info.warnings}
    assert codec.open_calls == [False]


def test_code_coverage() -> None:
    unreadable = frozenset({W.UNREADABLE})
    assert PROBE_CODES | unreadable | OWNED_ELSEWHERE == set(WarningCode)
    assert len(PROBE_CODES) == 11
    assert not PROBE_CODES & unreadable
    assert not PROBE_CODES & OWNED_ELSEWHERE
    assert not unreadable & OWNED_ELSEWHERE


DURATION_CASES = [
    ("clean.mp4", 5.0),
    ("av_mismatch.mp4", 3.0),
    ("start_offset.mp4", 5.52),
    ("no_audio.mp4", 3.0),
    ("music.m4a", 6.0),
    ("hdr10.mkv", 2.0),  # the stream duration is None: the container duration
    ("uhd_4k.mp4", 1.0),
]


@pytest.mark.parametrize(
    ("name", "expected"),
    DURATION_CASES,
    ids=[case[0] for case in DURATION_CASES],
)
def test_duration_s(name: str, expected: float) -> None:
    duration = probe(FIXTURES / name).duration_s
    assert duration is not None
    assert abs(duration - expected) <= 0.01
    if name == "uhd_4k.mp4":
        assert duration == 1.0  # exact Fraction arithmetic, never 0.999...


@pytest.mark.parametrize(
    ("start_time", "duration", "time_base", "container_start_s", "expected"),
    [
        (None, 3000, _MS, 0.0, (None, None)),
        (1520, None, _MS, 0.0, (1.52, None)),
        (1520, 4000, Fraction(0), 0.0, (None, None)),
        (1520, 4000, _MS, 0.0, (1.52, 5.52)),
        (0, 3000, _MS, -0.064, (0.064, 3.064)),
    ],
    ids=["start_none", "duration_none", "time_base_zero", "offset", "container_start_negative"],
)
@given(scale=st.integers(min_value=1, max_value=10**6))
def test_stream_clock(
    start_time: int | None,
    duration: int | None,
    time_base: Fraction,
    container_start_s: float,
    expected: tuple[float | None, float | None],
    scale: int,
) -> None:
    # The same instants in a finer time base (1/(1000 * scale)) must give the same floats
    # exactly: the arithmetic is exact Fraction, converted to float last.
    stream = _FakeStream(
        0,
        start_time=None if start_time is None else start_time * scale,
        duration=None if duration is None else duration * scale,
        time_base=time_base / scale,
    )
    got = (_stream_start_s(stream, container_start_s), _stream_end_s(stream, container_start_s))
    assert got == expected


@pytest.mark.parametrize("name", ["multi_audio.mkv", "music.m4a"])
def test_r4_fixture_indexes(name: str) -> None:
    info = probe(FIXTURES / name)
    if name == "multi_audio.mkv":
        assert info.video is not None
        assert info.video.index == 0
        assert [a.index for a in info.audio] == [1, 2]
        assert info.default_audio is not None
        assert info.default_audio.index == 1
    else:
        assert info.video is None
        assert info.audio[0].index == 0


@pytest.mark.parametrize("case", ["art_then_plain", "art_only"])
def test_select_video_skips_cover_art(case: str) -> None:
    art = _FakeStream(
        0, codec_context=_FakeCodec(name="mjpeg"), disposition=Disposition.attached_pic
    )
    if case == "art_then_plain":
        plain = _FakeStream(1)
        assert _select_video([art, plain]) is plain
    else:
        assert _select_video([art]) is None


def test_cover_art_m4a_in_process(tmp_path: Path) -> None:
    out = tmp_path / "cover.m4a"
    with av.open(str(out), "w", format="mp4") as container:
        audio = container.add_stream("aac", rate=16000, layout="mono")
        art = container.add_stream("mjpeg")
        art.width = 16
        art.height = 16
        art.pix_fmt = "yuvj420p"
        art.time_base = Fraction(1, 1)
        art.disposition = Disposition.attached_pic
        picture = VideoFrame.from_ndarray(np.zeros((16, 16, 3), np.uint8), format="rgb24")
        picture = picture.reformat(format="yuvj420p")
        picture.pts = 0
        container.mux(art.encode(picture))
        container.mux(art.encode(None))
        for i in range(16):
            samples = np.zeros((1, 1024), np.float32)
            frame = AudioFrame.from_ndarray(samples, format="fltp", layout="mono")
            frame.sample_rate = 16000
            frame.pts = i * 1024
            container.mux(audio.encode(frame))
        container.mux(audio.encode(None))
    info = probe(out)
    assert info.video is None
    assert len(info.audio) == 1


def _matrix(*m: int) -> bytes:
    return struct.pack("=9i", *m)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (None, 0),
        (bytes(35), 0),
        (bytes(36), 0),  # all zero: zero scale
        (_matrix(65536, 0, 0, 0, 65536, 0, 0, 0, _Q30), 0),
        (_matrix(0, -65536, 0, 65536, 0, 0, 0, 0, _Q30), 90),
        (_matrix(0, 65536, 0, -65536, 0, 0, 0, 0, _Q30), 270),
        (_matrix(-65536, 0, 0, 0, -65536, 0, 0, 0, _Q30), 180),
        (_matrix(46341, -46341, 0, 46341, 46341, 0, 0, 0, _Q30), 90),
        (_matrix(46341, 46341, 0, -46341, 46341, 0, 0, 0, _Q30), 0),
        (_matrix(47143, -45525, 0, 45525, 47143, 0, 0, 0, _Q30), 0),
    ],
    ids=[
        "none",
        "35_bytes",
        "zero_scale",
        "identity",
        "rot90",
        "rot270",
        "rot180",
        "plus45",
        "minus45",
        "plus44",
    ],
)
def test_rotation_from_matrix(data: bytes | None, expected: int) -> None:
    assert _rotation_from_matrix(data) == expected


@pytest.mark.parametrize("case", ["fixture", "copy"])
def test_unicode_path(tmp_path: Path, case: str) -> None:
    source = FIXTURES / "réunion 01.mp4"
    if case == "fixture":
        assert probe(source).path == source
    else:
        folder = tmp_path / "dossier é"
        folder.mkdir()
        copy = folder / "réunion 01.mp4"
        shutil.copyfile(source, copy)
        info = probe(copy)
        assert info.path == copy
        assert info.warnings == ()


@pytest.mark.parametrize("case", ["missing", "zero_byte", "directory"])
def test_bad_input_unreadable(tmp_path: Path, case: str) -> None:
    if case == "missing":
        path = tmp_path / "missing.mp4"
    elif case == "zero_byte":
        path = tmp_path / "empty.mp4"
        path.write_bytes(b"")
    else:
        path = tmp_path / "folder.mp4"
        path.mkdir()
    with pytest.raises(ProbeError) as raised:  # an av.error.* or OSError would fail here
        probe(path)
    assert raised.value.warning.code == W.UNREADABLE


@pytest.mark.parametrize("case", ["success", "asset_id_raises"])
def test_container_closed(monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    opened = _spy_on_open(monkeypatch)
    if case == "success":
        probe(FIXTURES / "clean.mp4")
    else:

        def broken_asset_id(*_args: object, **_kwargs: object) -> str:
            raise OSError(5, "Input/output error")

        monkeypatch.setattr("tapesift.media.probe.asset_id", broken_asset_id)
        with pytest.raises(ProbeError) as raised:
            probe(FIXTURES / "clean.mp4")
        assert raised.value.warning.code == W.UNREADABLE
    assert len(opened.containers) == 1
    assert opened.containers[0].exits == 1


def test_timeout_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = _spy_on_open(monkeypatch)
    probe(FIXTURES / "clean.mp4")
    assert opened.timeouts == [PROBE_TIMEOUT_S]
    assert PROBE_TIMEOUT_S == 30.0


def test_full_hash_id() -> None:
    clean = FIXTURES / "clean.mp4"
    assert probe(clean, full_hash=True).id == "sha256:" + BY_NAME["clean.mp4"]["sha256"]
    assert probe(clean).id.startswith("tsid1:")


def test_log_extras(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="tapesift.media.probe"):
        info = probe(FIXTURES / "clean.mp4")
    records = [r for r in caplog.records if r.name == "tapesift.media.probe"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.DEBUG
    assert record.getMessage() == "probed"
    assert getattr(record, "asset_id", None) == info.id
    assert getattr(record, "stage", None) == "probe"
