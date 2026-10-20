"""Tests for the shared safe opener (docs/specs/21-safe-opener.md, #21).

Every crafted file is built in tmp_path while the test runs. No test uses the network, and
the FIFO cases run the call in a daemon thread with a bounded join, so a regression fails
instead of hanging CI.
"""

from __future__ import annotations

import contextlib
import gc
import os
import shutil
import socket
import struct
import threading
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import av
import av.error
import numpy as np
import pytest
from av.audio.frame import AudioFrame
from av.audio.stream import AudioStream
from av.container import InputContainer
from av.video.frame import VideoFrame

from tapesift.media.decode import PyAVDecoder
from tapesift.media.probe import probe
from tapesift.media.safe_open import ALLOWED_FORMATS, OPEN_TIMEOUT_S, UnsafeInputError, open_media
from tapesift.media.types import AssetInfo, AudioStreamInfo, DecodeError, ProbeError, VideoInfo
from tapesift.warning_codes import AssetWarning, WarningCode

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN = FIXTURES / "clean.mp4"

UNSAFE_DETAIL = "container format not allowed or header invalid"
INVALID_DETAIL = "Invalid data found when processing input"
EXACT_OPTIONS = {
    "protocol_whitelist": "fd",
    "format_whitelist": "mov,matroska,avi,mpegts,wav,mp3,aac,flac,ogg",
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    def no_connect(*_a: object, **_k: object) -> None:
        raise AssertionError("network connection attempted")

    monkeypatch.setattr(socket.socket, "connect", no_connect)


# --- helpers ---------------------------------------------------------------------------


def RAW(p: Path, **extra: str) -> InputContainer:  # the spec's name for main's open
    """Main's open: a file: URL with only the file protocol allowed."""
    return av.open("file:" + str(p.resolve()), options={"protocol_whitelist": "file", **extra})


def _raw_names(p: Path) -> list[str]:
    with RAW(p) as c:
        return c.format.name.split(",")


def _neighbour(tmp: Path) -> Path:
    other = tmp / "other.mp4"
    shutil.copyfile(CLEAN, other)
    return other


def _video_packets(c: InputContainer, index: int = 0) -> int:
    """Packets with data on one video stream (demux also yields an empty flush packet)."""
    return sum(1 for pkt in c.demux(c.streams.video[index]) if pkt.size > 0)


def _is_unsafe(p: Path) -> None:
    with pytest.raises(UnsafeInputError) as raised:
        open_media(p)
    assert str(raised.value) == UNSAFE_DETAIL


def _is_invalid(p: Path) -> None:
    with pytest.raises(av.error.InvalidDataError) as raised:
        open_media(p)
    assert not isinstance(raised.value, UnsafeInputError)


def _write_audio(
    path: Path,
    muxer: str,
    codec: str,
    *,
    rate: int = 16_000,
    layout: str = "mono",
    bit_rate: int | None = None,
) -> Path:
    """1 s of silence."""
    with av.open(str(path), "w", format=muxer) as out:
        stream = cast("AudioStream", out.add_stream(codec, rate=rate, layout=layout))
        if bit_rate is not None:
            stream.bit_rate = bit_rate
        ctx = stream.codec_context
        done = 0
        while done < rate:
            n = ctx.frame_size or min(1024, rate - done)
            frame = AudioFrame(format=ctx.format.name, layout=layout, samples=n)
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            frame.sample_rate = rate
            frame.pts = done
            done += n
            for pkt in stream.encode(frame):
                out.mux(pkt)
        for pkt in stream.encode(None):
            out.mux(pkt)
    return path


def _remux_video(src: Path, dst: Path, muxer: str) -> Path:
    """Elementary stream from an existing file's video packets, with no encoder."""
    with av.open(str(src)) as inp, av.open(str(dst), "w", format=muxer) as out:
        stream = inp.streams.video[0]
        template = out.add_stream_from_template(stream)
        for pkt in inp.demux(stream):
            if pkt.dts is None:
                continue
            pkt.stream = template
            out.mux(pkt)
    return dst


def _write_m4v(path: Path) -> Path:
    with av.open(str(path), "w", format="m4v") as out:
        stream = out.add_stream("mpeg4", rate=25)
        stream.width = 64
        stream.height = 48
        stream.pix_fmt = "yuv420p"
        for _ in range(25):
            frame = VideoFrame.from_ndarray(np.zeros((48, 64, 3), np.uint8), format="rgb24")
            for pkt in stream.encode(frame):
                out.mux(pkt)
        for pkt in stream.encode(None):
            out.mux(pkt)
    return path


def _write_pngs(pattern: Path, count: int) -> None:
    with av.open(str(pattern), "w", format="image2") as out:
        stream = out.add_stream("png", rate=25)
        stream.width = 16
        stream.height = 16
        stream.pix_fmt = "rgb24"
        for i in range(count):
            frame = VideoFrame.from_ndarray(np.full((16, 16, 3), i * 40, np.uint8), "rgb24")
            for pkt in stream.encode(frame):
                out.mux(pkt)
        for pkt in stream.encode(None):
            out.mux(pkt)


def _craft_ffconcat(tmp: Path) -> Path:
    _neighbour(tmp)
    evil = tmp / "evil.mp4"
    evil.write_text("ffconcat version 1.0\nfile other.mp4\n", encoding="utf-8")
    return evil


_HLS = "#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXTINF:5,\nother.mp4\n#EXT-X-ENDLIST\n"


def _craft_hls_m3u8(tmp: Path) -> Path:
    _neighbour(tmp)
    evil = tmp / "evil.m3u8"
    evil.write_text(_HLS, encoding="utf-8")
    return evil


def _craft_hls_named_mp4(tmp: Path) -> Path:
    _neighbour(tmp)
    evil = tmp / "hls.mp4"
    evil.write_text(_HLS, encoding="utf-8")
    return evil


def _craft_image2(tmp: Path) -> Path:
    _neighbour(tmp)
    _write_pngs(tmp / "seq%03d.png", 3)  # seq001.png .. seq003.png
    pattern = tmp / "seq%03d.png"
    shutil.copyfile(tmp / "seq001.png", pattern)  # the file we are handed
    return pattern


def _craft_png_named_mp4(tmp: Path) -> Path:
    _neighbour(tmp)
    _write_pngs(tmp / "seq%03d.png", 3)
    frame = tmp / "frame.mp4"
    shutil.copyfile(tmp / "seq001.png", frame)
    return frame


def _craft_tty_nfo(tmp: Path) -> Path:
    _neighbour(tmp)
    art = tmp / "art.nfo"
    art.write_text("hello ansi\n" * 20, encoding="utf-8")
    return art


def _craft_srt(tmp: Path) -> Path:
    _neighbour(tmp)
    subs = tmp / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n\n", encoding="utf-8")
    return subs


def _craft_sdp(tmp: Path) -> Path:
    _neighbour(tmp)
    sdp = tmp / "x.sdp"
    sdp.write_text(
        "v=0\no=- 0 0 IN IP4 127.0.0.1\ns=x\nc=IN IP4 127.0.0.1\nt=0 0\nm=audio 9 RTP/AVP 0\n",
        encoding="utf-8",
    )
    return sdp


def _craft_mov_dref(tmp: Path) -> Path:
    """clean.mp4 with video track 0 pointing at other.mp4 through an `alis` dref entry, and the
    file's own mdat zeroed. clean.mp4's top level is ftyp, free, mdat, moov, so no chunk offset
    moves."""
    _neighbour(tmp)
    path = b"/x/other.mp4"
    alis = (
        struct.pack(">I", 0)
        + bytes(10)
        + b"\x00"
        + bytes(27)
        + bytes(12)
        + bytes([9])
        + b"other.mp4".ljust(63, b"\x00")
        + bytes(16)
        + struct.pack(">HH", 1, 1)
        + bytes(16)
        + struct.pack(">HH", 2, len(path))
        + path
        + struct.pack(">hH", -1, 0)
    )
    entry = struct.pack(">I", 8 + len(alis)) + b"alis" + alis
    dref_body = struct.pack(">II", 0, 1) + entry
    containers = {b"moov", b"trak", b"mdia", b"minf", b"dinf"}
    seen_trak: list[int] = []

    def rewrite(buf: bytes) -> bytes:
        out = b""
        pos = 0
        while pos < len(buf):
            size, kind = struct.unpack_from(">I4s", buf, pos)
            body = buf[pos + 8 : pos + size]
            if kind == b"trak":
                seen_trak.append(1)
            if kind in containers:
                body = rewrite(body)
            elif kind == b"dref" and len(seen_trak) == 1:
                body = dref_body
            elif kind == b"mdat":
                body = bytes(len(body))
            out += struct.pack(">I4s", 8 + len(body), kind) + body
            pos += size
        return out

    evil = tmp / "evil.mov"
    evil.write_bytes(rewrite(CLEAN.read_bytes()))
    return evil


Craft = Callable[[Path], Path]
CRAFT: dict[str, Craft] = {
    "ffconcat_mp4": _craft_ffconcat,
    "hls_m3u8": _craft_hls_m3u8,
    "hls_named_mp4": _craft_hls_named_mp4,
    "image2_sequence": _craft_image2,
    "png_named_mp4": _craft_png_named_mp4,
    "tty_nfo": _craft_tty_nfo,
    "srt": _craft_srt,
    "sdp": _craft_sdp,
    "mov_dref": _craft_mov_dref,
}


def _asset(path: Path, audio: bool = False) -> AssetInfo:
    return AssetInfo(
        "tsid1:" + "0" * 64,
        path,
        5.0,
        VideoInfo(0, "h264", 320, 240, 25.0, False, 0),
        (AudioStreamInfo(1, "aac", None, True),) if audio else (),
        (),
    )


def _run_bounded(fifo: Path, call: Callable[[], object]) -> BaseException | None:
    """FIFO pattern: run `call` in a daemon thread, fail (never hang) when it is still alive after
    5 s, and always unblock a stuck open before the final join. Returns what `call` raised."""
    raised: list[BaseException] = []

    def target() -> None:
        try:
            call()
        except BaseException as e:
            raised.append(e)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    try:
        thread.join(5)
        assert not thread.is_alive(), "call blocked on the FIFO"
    finally:
        if thread.is_alive():
            with contextlib.suppress(OSError):
                os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            thread.join(5)
    return raised[0] if raised else None


@dataclass
class _Call:
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


def _record_open(
    monkeypatch: pytest.MonkeyPatch, extra_options: dict[str, str] | None = None
) -> list[_Call]:
    """Wraps av.open, records each call, and calls the real one (with extra options, if given)."""
    real_open: Callable[..., Any] = av.open
    calls: list[_Call] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls.append(_Call(args, {**kwargs, "options": dict(kwargs["options"])}))
        if extra_options is not None:
            kwargs["options"] = {**kwargs["options"], **extra_options}
        return real_open(*args, **kwargs)

    monkeypatch.setattr("tapesift.media.safe_open.av.open", wrapper)
    return calls


def _check_exact_call(call: _Call) -> None:
    assert call.args == ("fd:",)
    assert call.kwargs["timeout"] == 30.0
    options = dict(call.kwargs["options"])
    assert options.pop("fd").isdigit()
    assert options == EXACT_OPTIONS


# --- allowed formats ---------------------------------------------------------------------

ALLOWED_IDS = ["mov", "matroska", "avi", "mpegts", "wav", "mp3", "aac", "flac", "ogg"]


@pytest.mark.parametrize(
    ("name", "file", "muxer", "codec"),
    [
        ("mov", "a.m4a", "mp4", "aac"),
        ("matroska", "a.mkv", "matroska", "flac"),
        ("avi", "a.avi", "avi", "pcm_s16le"),
        ("mpegts", "a.ts", "mpegts", "mp2"),
        ("wav", "a.wav", "wav", "pcm_s16le"),
        ("mp3", "a.mp2", "mp2", "mp2"),
        ("aac", "a.aac", "adts", "aac"),
        ("flac", "a.flac", "flac", "flac"),
        ("ogg", "a.ogg", "ogg", "flac"),
    ],
    ids=ALLOWED_IDS,
)
def test_allowed_format_opens(tmp_path: Path, name: str, file: str, muxer: str, codec: str) -> None:
    path = _write_audio(tmp_path / file, muxer, codec)
    with open_media(path) as c:
        assert name in c.format.name.split(",")
    if name == "mov":
        assert tuple(ALLOWED_IDS) == ALLOWED_FORMATS


# --- formats that are refused ------------------------------------------------------------


def _make_h264(p: Path) -> Path:
    return _remux_video(CLEAN, p, "h264")


def _make_hevc(p: Path) -> Path:
    return _remux_video(FIXTURES / "hdr10.mkv", p, "hevc")


def _make_amr(p: Path) -> Path:
    p.write_bytes(b"#!AMR\n" + bytes([0x3C] + [0] * 31) * 50)
    return p


def _audio_maker(muxer: str, codec: str, **kw: Any) -> Callable[[Path], Path]:
    return lambda p: _write_audio(p, muxer, codec, **kw)


REFUSED_FAMILIES: dict[str, tuple[str, Callable[[Path], Path]]] = {
    "h264": ("raw.h264", _make_h264),
    "hevc": ("raw.hevc", _make_hevc),
    "m4v": ("raw.m4v", _write_m4v),
    "ac3": ("a.ac3", _audio_maker("ac3", "ac3", rate=48_000, layout="stereo")),
    "eac3": ("a.eac3", _audio_maker("eac3", "eac3", rate=48_000, layout="stereo")),
    "mpeg": ("a.mpg", _audio_maker("mpeg", "mp2")),
    "aiff": ("a.aiff", _audio_maker("aiff", "pcm_s16be")),
    "flv": ("a.flv", _audio_maker("flv", "aac", rate=44_100)),
    "asf": (
        "a.wma",
        _audio_maker("asf", "wmav2", rate=44_100, layout="stereo", bit_rate=128_000),
    ),
    "amr": ("a.amr", _make_amr),
    "caf": ("a.caf", _audio_maker("caf", "pcm_s16le")),
    "w64": ("a.w64", _audio_maker("w64", "pcm_s16le")),
}


@pytest.mark.parametrize("case", list(REFUSED_FAMILIES))
def test_refused_family(tmp_path: Path, case: str) -> None:
    file, make = REFUSED_FAMILIES[case]
    path = make(tmp_path / file)
    assert case in _raw_names(path)  # main's open reads it as this demuxer
    if case == "hevc":
        _is_invalid(path)
    else:
        _is_unsafe(path)
    with pytest.raises(ProbeError) as raised:
        probe(path)
    assert raised.value.warning.code == WarningCode.UNREADABLE


# --- indirection: demuxers that read other files ------------------------------------------

REFUSED_DEMUXERS: list[tuple[str, bool]] = [  # (craft case, expects UNSAFE rather than INVALID)
    ("ffconcat_mp4", True),
    ("hls_m3u8", False),
    ("hls_named_mp4", False),
    ("image2_sequence", True),
    ("png_named_mp4", True),
    ("tty_nfo", False),
    ("srt", True),
    ("sdp", True),
]


@pytest.mark.parametrize(
    ("case", "unsafe"), REFUSED_DEMUXERS, ids=[case for case, _ in REFUSED_DEMUXERS]
)
def test_refused_demuxer(tmp_path: Path, case: str, unsafe: bool) -> None:
    path = CRAFT[case](tmp_path)
    if unsafe:
        _is_unsafe(path)
    else:
        _is_invalid(path)


@pytest.mark.parametrize("case", ["ffconcat_mp4", "hls_m3u8", "image2_sequence", "mov_dref"])
def test_attack_is_live_without_allow_list(tmp_path: Path, case: str) -> None:
    path = CRAFT[case](tmp_path)
    if case == "mov_dref":
        with RAW(path, enable_drefs="1") as c:
            assert _video_packets(c) == 125
        return
    with RAW(path) as c:
        names = c.format.name.split(",")
        if case == "ffconcat_mp4":
            assert "concat" in names
            assert len(c.streams) == 2
        elif case == "hls_m3u8":
            assert "hls" in names
            assert len(c.streams) == 2
        else:
            assert "image2" in names
            assert _video_packets(c) == 3  # seq001.png .. seq003.png; the literal file is not one


@pytest.mark.parametrize("case", ["default", "forced_on"])
def test_mov_dref_not_followed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str) -> None:
    evil = _craft_mov_dref(tmp_path)
    if case == "forced_on":
        monkeypatch.chdir(tmp_path)
        _record_open(monkeypatch, {"enable_drefs": "1"})
    with open_media(evil) as c:
        assert "mov" in c.format.name.split(",")
        assert _video_packets(c) == 0


@pytest.mark.parametrize("case", ["ffconcat_mp4", "image2_sequence", "hls_m3u8"])
def test_probe_refuses_indirection(tmp_path: Path, case: str) -> None:
    path = CRAFT[case](tmp_path)
    with pytest.raises(ProbeError) as raised:
        probe(path)
    assert raised.value.warning.code == WarningCode.UNREADABLE
    if case == "hls_m3u8":
        assert raised.value.warning.detail == f"InvalidDataError: {INVALID_DETAIL}"
    else:
        assert raised.value.warning.detail == f"UnsafeInputError: {UNSAFE_DETAIL}"


@pytest.mark.parametrize("case", ["ffconcat_mp4", "image2_sequence", "hls_m3u8"])
def test_decode_refuses_indirection(tmp_path: Path, case: str) -> None:
    path = CRAFT[case](tmp_path)
    sink: list[AssetWarning] = []
    with pytest.raises(DecodeError) as raised:
        next(PyAVDecoder().iter_frames(_asset(path), None, warn=sink.append))
    assert raised.value.warning.code == WarningCode.UNREADABLE
    detail = raised.value.warning.detail
    if case == "hls_m3u8":
        assert detail.startswith("cannot open: ")
        assert INVALID_DETAIL in detail
    else:
        assert detail == f"cannot open: {UNSAFE_DETAIL}"
    assert sink == []


# --- files that are not regular files -----------------------------------------------------


@pytest.mark.parametrize(
    "case", ["directory", "fifo", "char_device", "symlink_to_fifo", "symlink_to_char_device"]
)
def test_non_regular_refused(tmp_path: Path, case: str) -> None:
    fifo = tmp_path / "pipe.fifo"
    if case == "directory":
        path = tmp_path / "folder.mp4"
        path.mkdir()
    elif case == "fifo":
        path = tmp_path / "pipe.mp4"
        os.mkfifo(path)
        fifo = path
    elif case == "char_device":
        path = Path("/dev/null")
    elif case == "symlink_to_fifo":
        os.mkfifo(fifo)
        path = tmp_path / "link.mp4"
        path.symlink_to(fifo)
    else:
        path = tmp_path / "link.mp4"
        path.symlink_to("/dev/null")
    kind = {
        "directory": "directory",
        "fifo": "fifo",
        "char_device": "character device",
        "symlink_to_fifo": "fifo",
        "symlink_to_char_device": "character device",
    }[case]
    raised = _run_bounded(fifo, lambda: open_media(path))
    assert isinstance(raised, UnsafeInputError)
    assert str(raised) == f"not a regular file: {kind}"


@pytest.mark.parametrize("stage", ["probe", "frames", "audio"])
def test_stages_refuse_fifo_without_blocking(tmp_path: Path, stage: str) -> None:
    fifo = tmp_path / "pipe.mp4"
    os.mkfifo(fifo)
    asset = _asset(fifo, audio=True)
    sink: list[AssetWarning] = []
    if stage == "probe":
        raised = _run_bounded(fifo, lambda: probe(fifo))
        assert isinstance(raised, ProbeError)
        assert raised.warning.code == WarningCode.UNREADABLE
        assert raised.warning.detail == "UnsafeInputError: not a regular file: fifo"
        return
    decoder = PyAVDecoder()
    if stage == "frames":
        raised = _run_bounded(
            fifo, lambda: next(decoder.iter_frames(asset, None, warn=sink.append))
        )
    else:
        raised = _run_bounded(fifo, lambda: next(decoder.iter_audio(asset, warn=sink.append)))
    assert isinstance(raised, DecodeError)
    assert raised.warning.code == WarningCode.UNREADABLE
    assert raised.warning.detail == "cannot open: not a regular file: fifo"


def test_swap_to_fifo_after_stat_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fifo = tmp_path / "pipe.mp4"
    os.mkfifo(fifo)
    real_stat = os.stat

    def swapped_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if os.fspath(path) == str(fifo):
            return real_stat(CLEAN)  # step 1 sees a regular file; the swap came after it
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr("tapesift.media.safe_open.os.stat", swapped_stat)
    raised = _run_bounded(fifo, lambda: open_media(fifo))
    assert isinstance(raised, UnsafeInputError)
    assert str(raised) == "not a regular file: fifo"


# --- what still opens, and errors that pass through ---------------------------------------


def test_symlink_to_media_opens(tmp_path: Path) -> None:
    link = tmp_path / "link.mp4"
    link.symlink_to(CLEAN)
    with open_media(link) as c:
        assert "mov" in c.format.name.split(",")
    assert probe(link).duration_s == 5.0


@pytest.mark.parametrize("case", ["missing", "dangling_symlink", "no_permission"])
def test_open_os_errors_pass_through(tmp_path: Path, case: str) -> None:
    if case == "missing":
        path = tmp_path / "gone.mp4"
    elif case == "dangling_symlink":
        path = tmp_path / "dangling.mp4"
        path.symlink_to(tmp_path / "gone.mp4")
    else:
        path = tmp_path / "locked.mp4"
        shutil.copyfile(CLEAN, path)
        path.chmod(0)
    expected = PermissionError if case == "no_permission" else FileNotFoundError
    try:
        with pytest.raises(expected) as raised:
            open_media(path)
    finally:
        if case == "no_permission":
            path.chmod(0o644)
    assert not isinstance(raised.value, UnsafeInputError)
    expected_msg = "Permission denied" if case == "no_permission" else "No such file or directory"
    assert raised.value.strerror == expected_msg


def test_other_open_errors_pass_through() -> None:
    with pytest.raises(av.error.InvalidDataError) as raised:
        open_media(FIXTURES / "not_media.txt")
    assert not isinstance(raised.value, UnsafeInputError)


@pytest.mark.parametrize(
    "name", ["a #1.mp4", "50% d%03d.mp4", "what?.mp4", "réunion é 01.mp4", "file:z.mp4"]
)
def test_unusual_names_open(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    shutil.copyfile(CLEAN, path)
    with open_media(path) as c:
        assert "mov" in c.format.name.split(",")
    assert probe(path).duration_s == 5.0


# --- the exact call, and what it leaks -----------------------------------------------------


def test_open_call_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record_open(monkeypatch)
    open_media(CLEAN).close()
    assert len(calls) == 1
    _check_exact_call(calls[0])
    assert OPEN_TIMEOUT_S == 30.0


def _fd_count() -> int:
    gc.collect()
    return len(list(Path("/dev/fd").iterdir()))


def test_no_fd_leak(tmp_path: Path) -> None:
    evil = _craft_ffconcat(tmp_path)
    fifo = tmp_path / "pipe.mp4"
    os.mkfifo(fifo)
    not_media = FIXTURES / "not_media.txt"
    before = _fd_count()
    for _ in range(20):
        open_media(CLEAN).close()
        with pytest.raises(UnsafeInputError):
            open_media(evil)
        with pytest.raises(UnsafeInputError):
            open_media(fifo)
        with pytest.raises(av.error.InvalidDataError):
            open_media(not_media)
    assert _fd_count() == before


@pytest.mark.parametrize("stage", ["probe", "decode"])
def test_stages_pass_allow_list_and_timeout(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    calls = _record_open(monkeypatch)
    if stage == "probe":
        probe(CLEAN)
    else:
        sink: list[AssetWarning] = []
        frames = PyAVDecoder().iter_frames(_asset(CLEAN), None, warn=sink.append)
        next(frames)
        cast("Generator[object]", frames).close()
    assert len(calls) == 1
    _check_exact_call(calls[0])
