"""Issue #12: probe() then PyAVDecoder over every manifest fixture, end to end.
Specs: docs/specs/5-probe.md (what probe reports), 6-decode.md and 4-media-types.md R3, R5-R8, R10
(what decode must do with it). Test-only: decode is given the AssetInfo probe built, never a
hand-made one (test_decode.py does the hand-made ones)."""

import itertools
import json
from typing import Any

import pytest
from conftest import FIXTURES

# test_decode builds PyAVDecoder() once at import; reuse its helpers rather than copy them.
from test_decode import D, _joined, _partials  # pyright: ignore[reportPrivateUsage]

from tapesift.media.probe import probe
from tapesift.media.types import (
    EARLY_EOF_S,
    MAX_SIDE_PX,
    AssetInfo,
    AudioChunk,
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
    # R5: probe's w/h are stored; upright swaps them for 90/270. R6: only shrinks, long side
    # <= MAX_SIDE_PX, each side within half a pixel of exact scaling (+1 for filter rounding).
    dw, dh = (video.h, video.w) if video.rotation in (90, 270) else (video.w, video.h)
    scale = min(1.0, MAX_SIDE_PX / max(dw, dh))
    for f in frames:
        h, w, c = f.pixels.shape
        assert c == 3
        assert max(h, w) <= MAX_SIDE_PX
        if scale == 1.0:
            assert (w, h) == (dw, dh)
        else:
            assert max(h, w) == MAX_SIDE_PX
            assert abs(w - dw * scale) <= 1
            assert abs(h - dh * scale) <= 1


def _check_audio(info: AssetInfo, chunks: list[AudioChunk], sink: list[AssetWarning]) -> None:
    default = info.default_audio
    assert default is not None
    assert chunks
    assert chunks[0].start_s >= 0
    assert all(c.sample_rate == _RATE for c in chunks)
    # R3/R4: track=None is audio[index of default_audio]; the explicit call gives the same bytes.
    explicit = list(D.iter_audio(info, track=info.audio.index(default), warn=[].append))
    assert _joined(explicit).tolist() == _joined(chunks).tolist()
    if len(info.audio) > 1:  # and a different track really is different audio
        other = next(i for i, a in enumerate(info.audio) if a is not default)
        other_chunks = list(D.iter_audio(info, track=other, warn=[].append))
        assert _joined(other_chunks).tolist() != _joined(chunks).tolist()
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
