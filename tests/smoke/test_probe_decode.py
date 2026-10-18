"""Issue #12: probe() then PyAVDecoder over every manifest fixture, end to end.
Specs: docs/specs/5-probe.md (what probe reports), 6-decode.md and 4-media-types.md R3, R5-R8, R10
(what decode must do with it). Test-only: decode is given the AssetInfo probe built, never a
hand-made one (test_decode.py does the hand-made ones)."""

import contextlib
import itertools
import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import FIXTURES

# test_decode builds PyAVDecoder() once at import; reuse its helpers rather than copy them.
from test_decode import (  # pyright: ignore[reportPrivateUsage]
    D,
    _joined,
    _partials,
    _patch_open,
    _peak_hz,
)

from tapesift.media.decode import upright_size
from tapesift.media.probe import probe
from tapesift.media.types import (
    EARLY_EOF_S,
    MAX_SIDE_PX,
    AssetInfo,
    AudioChunk,
    AudioStreamInfo,
    DecodeError,
    Frame,
    ProbeError,
)
from tapesift.warning_codes import AssetWarning, WarningCode

W = WarningCode
_RATE = 16_000  # iter_audio's default sample_rate
# Manifest codes that no probe or decode stage emits (docs/specs/5-probe.md, "Not emitted by
# probe"; PARTIAL_DECODE is decode's and is kept).
_OWNED_ELSEWHERE = frozenset({W.CROPPED, W.LOW_SPEECH, W.MEDIA_TEXT, W.DUPLICATE})

_ENTRIES: list[Any] = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))[
    "fixtures"
]

_AAC = (AudioStreamInfo(1, "aac", "und", True),)
_H264 = ("h264", 320, 240)
# docs/specs/6-decode.md, Acceptance table (ffprobe values): (duration_s, video index, codec, w, h,
# fps_avg, vfr, rotation, audio). Probe must reproduce these, or "decode agrees with probe" could
# pass with both wrong.
_PINNED: dict[
    str, tuple[float, int, str, int, int, float, bool, int, tuple[AudioStreamInfo, ...]]
] = {
    "vfr.mp4": (5.933333, 0, *_H264, 1500 / 89, True, 0, ()),
    "start_offset.mp4": (5.52, 0, *_H264, 25.0, False, 0, _AAC),
    "multi_audio.mkv": (
        3.064,
        0,
        *_H264,
        25.0,
        False,
        0,
        (AudioStreamInfo(1, "aac", "eng", True), AudioStreamInfo(2, "aac", "eng", False)),
    ),
    "rotated.mp4": (5.0, 0, *_H264, 25.0, False, 90, _AAC),
    "rotated_270.mp4": (1.0, 0, *_H264, 5.0, False, 270, ()),
}


def _check_pinned(name: str, info: AssetInfo) -> None:
    dur, index, codec, w, h, fps, vfr, rot, audio = _PINNED[name]
    assert info.duration_s == pytest.approx(dur, abs=1e-6)
    video = info.video
    assert video is not None
    assert (video.index, video.codec, video.w, video.h) == (index, codec, w, h)
    assert video.fps_avg == pytest.approx(fps, rel=1e-6)
    assert (video.vfr, video.rotation) == (vfr, rot)
    assert info.audio == audio


def _side(kind: str, ws: list[AssetWarning]) -> list[AssetWarning]:
    """PARTIAL_DECODE warnings for one stream kind, "video" or "audio" (R10 detail prefix)."""
    return [w for w in _partials(ws) if w.detail.startswith(kind + " stream")]


def _check_frames(info: AssetInfo, frames: list[Frame], sink: list[AssetWarning]) -> None:
    video = info.video
    assert video is not None
    assert frames
    ts = [f.t_s for f in frames]
    assert all(a < b for a, b in itertools.pairwise(ts))  # R7 step 2
    assert ts[0] >= 0  # R7 step 1
    if info.duration_s is not None:
        assert ts[-1] < info.duration_s  # R7 step 1 drops t_s >= duration_s
        # R10: a clean EOF more than EARLY_EOF_S before duration_s is a PARTIAL_DECODE run, so
        # either the frames reach that close to the end or decode said it lost the tail.
        assert ts[-1] >= info.duration_s - EARLY_EOF_S or _side("video", sink)
    assert video.w is not None
    assert video.h is not None
    # R5: probe's w/h are stored; the upright size swaps them for 90/270. R6: upright_size is the
    # exact rule (round half up, long side <= MAX_SIDE_PX).
    dw, dh = (video.h, video.w) if video.rotation in (90, 270) else (video.w, video.h)
    for f in frames:
        assert f.pixels.shape == (*upright_size(dh, dw), 3)
        assert max(f.pixels.shape[:2]) <= MAX_SIDE_PX


def _check_audio(info: AssetInfo, chunks: list[AudioChunk], sink: list[AssetWarning]) -> None:
    default = info.default_audio
    assert default is not None
    assert chunks
    assert chunks[0].start_s >= 0
    assert all(c.sample_rate == _RATE for c in chunks)
    assert all(c.samples.ndim == 1 and c.samples.dtype == np.float32 for c in chunks)
    if info.path.name != "silence.mp4":  # the manifest's one digital-silence fixture
        assert float(np.abs(_joined(chunks)).max()) > 0
    # R3/R4: track=None is audio[index of default_audio]; the explicit call gives the same bytes.
    explicit = list(D.iter_audio(info, track=info.audio.index(default), warn=[].append))
    assert _joined(explicit).tolist() == _joined(chunks).tolist()
    if info.duration_s is None:
        return
    last = chunks[-1]
    assert last.start_s + (last.samples.size - 1) / _RATE < info.duration_s  # R3: clipped
    # Duration match, tolerance EARLY_EOF_S: audio may end up to that early (AAC padding, a
    # start-offset video, 6 s audio under a 3 s video is clipped, not short) without a warning;
    # anything shorter must have been reported as an audio PARTIAL_DECODE (R10).
    end_s = last.start_s + last.samples.size / _RATE
    assert end_s >= info.duration_s - EARLY_EOF_S or _side("audio", sink)


@pytest.mark.parametrize("entry", _ENTRIES, ids=[e["name"] for e in _ENTRIES])
def test_probe_then_decode(entry: Any) -> None:
    path = FIXTURES / entry["name"]
    manifest_codes = {WarningCode(c) for c in entry["warning_codes"]}
    try:
        info = probe(path)
    except ProbeError as e:
        # Probe rejects it: the manifest must say UNREADABLE, and decode is never reached
        # (this test only builds an AssetInfo after probe returns one).
        assert e.warning.code is W.UNREADABLE
        assert W.UNREADABLE in manifest_codes
        return
    assert W.UNREADABLE not in manifest_codes
    if entry["name"] in _PINNED:
        _check_pinned(entry["name"], info)

    seen = {w.code for w in info.warnings}
    sink: list[AssetWarning] = []
    frames: list[Frame] = []
    chunks: list[AudioChunk] = []

    # R10: DecodeError is decided from the stream itself; probe says "unknown" exactly when
    # FFmpeg has no decoder for the video stream.
    no_decoder = info.video is not None and info.video.codec == "unknown"
    if info.video is None:
        assert list(D.iter_frames(info, None, warn=sink.append)) == []
    elif no_decoder:
        with pytest.raises(DecodeError) as err:
            next(D.iter_frames(info, None, warn=sink.append))
        seen.add(err.value.warning.code)
        assert err.value.warning.code is W.UNSUPPORTED_CODEC
    else:
        frames = list(D.iter_frames(info, None, warn=sink.append))
        _check_frames(info, frames, sink)

    if not info.audio:
        assert list(D.iter_audio(info, warn=sink.append)) == []  # R8: nothing, no warning
    else:
        chunks = list(D.iter_audio(info, warn=sink.append))
        _check_audio(info, chunks, sink)

    seen |= {w.code for w in sink}
    assert {w.code for w in sink} <= {W.PARTIAL_DECODE}  # the only code decode warns with
    # Probe and decode together report exactly the manifest's codes that these two stages own;
    # NO_AUDIO is probe's on video-only fixtures, which the manifest does not list.
    expected = manifest_codes - _OWNED_ELSEWHERE
    if info.video is not None and not info.audio:
        expected.add(W.NO_AUDIO)
    assert seen == expected


# ---- the cases the loop above cannot see: values pinned to the specs ----


def _first_frame(name: str) -> Frame:
    return next(D.iter_frames(probe(FIXTURES / name), None, warn=[].append))


def test_rotation_direction_pixels() -> None:
    # spec 6-decode row 5. 270 and 90 give the same shape, so only pixels pin the direction.
    px = _first_frame("rotated_270.mp4").pixels
    assert px.shape == (320, 240, 3)
    red, blue = px[160, 230].astype(int), px[160, 10].astype(int)  # red right, blue left
    assert red[0] > 200
    assert red[2] < 60
    assert blue[2] > 200
    assert blue[0] < 60
    # rotated.mp4 is clean.mp4 plus a 90 deg display matrix: exactly one quarter turn.
    assert np.array_equal(
        _first_frame("rotated.mp4").pixels, np.rot90(_first_frame("clean.mp4").pixels, 1)
    )


def test_start_offset_times() -> None:
    # spec 6-decode row 4 (line 253): video starts 1.52 s in, audio at 0; clean starts at 0.
    info = probe(FIXTURES / "start_offset.mp4")
    assert next(D.iter_frames(info, None, warn=[].append)).t_s == pytest.approx(1.52, abs=0.04)
    assert 0.0 <= next(D.iter_audio(info, warn=[].append)).start_s <= 0.002
    assert _first_frame("clean.mp4").t_s == pytest.approx(0.0, abs=0.002)


def test_container_start_shifts_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    # R1: audio times subtract the container start too (the frames twin is in test_decode.py).
    info = probe(FIXTURES / "clean.mp4")
    _patch_open(monkeypatch, start_time=-1_000_000)  # container starts at -1 s
    first = next(D.iter_audio(info, warn=[].append))
    assert first.start_s == pytest.approx(1.0, abs=0.003)


def test_default_track_by_content() -> None:
    # multi_audio.mkv: stream 1 (the default) is 440 Hz, stream 2 is 660 Hz (make_fixtures.py).
    info = probe(FIXTURES / "multi_audio.mkv")
    assert info.default_audio == info.audio[0]
    default = list(D.iter_audio(info, warn=[].append))
    other = list(D.iter_audio(info, track=1, warn=[].append))
    assert abs(_peak_hz(_joined(default), _RATE) - 440) <= 2
    assert abs(_peak_hz(_joined(other), _RATE) - 660) <= 2


def test_a_multi_track_fixture_exists() -> None:
    # Keeps the track tests above from going vacuous if the manifest changes.
    counts: list[int] = []
    for e in _ENTRIES:
        with contextlib.suppress(ProbeError):
            counts.append(len(probe(FIXTURES / e["name"]).audio))
    assert max(counts) > 1


def test_truncated_partial_decode_details() -> None:
    info = probe(FIXTURES / "truncated.mp4")
    assert info.duration_s is not None
    end = f"{info.duration_s:.2f}"  # the gap runs to duration_s (R10)
    vsink: list[AssetWarning] = []
    frames = list(D.iter_frames(info, None, warn=vsink.append))
    # A starts where the last good frame left off: its t_s.
    assert [w.detail for w in _partials(vsink)] == [
        f"video stream 0: undecodable {frames[-1].t_s:.2f}-{end} s"
    ]
    asink: list[AssetWarning] = []
    chunks = list(D.iter_audio(info, warn=asink.append))
    # For audio, the last good sample's end.
    a_end = chunks[-1].start_s + chunks[-1].samples.size / _RATE
    details = [w.detail for w in _partials(asink)]
    assert details == [f"audio stream 1: undecodable {a_end:.2f}-{end} s"]
    m = re.fullmatch(r"audio stream 1: undecodable (\d+\.\d\d)-6\.00 s", details[0])
    assert m is not None
    assert 3.0 <= float(m.group(1)) < 6.0


def test_unreadable_after_probe(tmp_path: Path) -> None:
    # A file that probed fine and then vanished: decode reports UNREADABLE, it does not crash.
    path = tmp_path / "gone.mp4"
    shutil.copyfile(FIXTURES / "clean.mp4", path)
    info = probe(path)
    path.unlink()
    with pytest.raises(DecodeError) as video:
        next(D.iter_frames(info, None, warn=[].append))
    assert video.value.warning.code is W.UNREADABLE
    with pytest.raises(DecodeError) as audio:
        next(D.iter_audio(info, warn=[].append))
    assert audio.value.warning.code is W.UNREADABLE
