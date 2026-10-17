import hashlib
import json
import re
from pathlib import Path

import pytest

from tapesift.media.asset_id import CHUNK_BYTES, SCHEME, asset_id

FIXTURES = Path(__file__).parents[1] / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = MANIFEST["fixtures"]
BY_NAME = {e["name"]: e for e in ENTRIES}

ID_SHAPE = re.compile(r"^(tsid1|sha256):[0-9a-f]{64}$")
MIB = 1024 * 1024
CHUNK = 8 * MIB  # written out, not imported, so the expected IDs stay independent
SIZE_40MIB = 40 * MIB

# Pinned from the spec's reference implementation (docs/specs/5-probe.md), run outside the
# repo on the committed fixtures and on the 40 MiB pattern file.
PINNED_CLEAN = "tsid1:cf5469acfe8f4027b6de778f12d1ea7783a9484ef65343bcb1bdf829d287a860"
PINNED_REUNION = "tsid1:ca16a762f62f80c983442441daccc4b2b2bffafeb6452f391e5ce29ed95ed430"
PINNED_40MIB = "tsid1:96feedd23c3de89a1f98c491c0e9d5ae33e650fc0ab914fc878650fc226dae16"


def _pattern(n: int) -> bytes:
    k = n // 251 + 1
    return (bytes(range(251)) * k)[:n]


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _independent_id(data: bytes) -> str:
    n = len(data)
    head = data[:CHUNK]
    tail = data[max(CHUNK, n - CHUNK) :]
    return "tsid1:" + hashlib.sha256(n.to_bytes(8, "big") + head + tail).hexdigest()


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["name"] for e in ENTRIES])
def test_full_id_matches_manifest(entry: dict[str, object]) -> None:
    got = asset_id(FIXTURES / str(entry["name"]), full=True)
    assert got == "sha256:" + str(entry["sha256"])
    assert ID_SHAPE.match(got)


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["name"] for e in ENTRIES])
def test_default_id_shape(entry: dict[str, object]) -> None:
    got = asset_id(FIXTURES / str(entry["name"]))
    assert ID_SHAPE.match(got)
    assert got.startswith("tsid1:")
    assert got != "tsid1:" + str(entry["sha256"])  # the size prefix is always hashed


def test_pinned_fixture_vectors() -> None:
    assert (SCHEME, CHUNK_BYTES) == ("tsid1", 8 * MIB)  # the pins are only valid for tsid1
    assert asset_id(FIXTURES / "clean.mp4") == PINNED_CLEAN
    assert asset_id(FIXTURES / "réunion 01.mp4") == PINNED_REUNION


def test_pinned_40mib_vector(tmp_path: Path) -> None:
    path = _write(tmp_path / "pattern.bin", _pattern(SIZE_40MIB))
    assert asset_id(path) == PINNED_40MIB


def test_duplicate_ids_match() -> None:
    assert asset_id(FIXTURES / "clean.mp4") == asset_id(FIXTURES / "clean_copy.mp4")


@pytest.mark.parametrize(
    "n",
    [0, 1, 8 * MIB, 8 * MIB + 1, 16 * MIB, 16 * MIB + 1],
    ids=["0", "1", "8MiB", "8MiB+1", "16MiB", "16MiB+1"],
)
def test_boundary_sizes(tmp_path: Path, n: int) -> None:
    data = _pattern(n)
    path = _write(tmp_path / "boundary.bin", data)
    assert asset_id(path) == _independent_id(data)


def test_middle_byte_collides(tmp_path: Path) -> None:
    data = bytearray(_pattern(SIZE_40MIB))
    path = _write(tmp_path / "pattern.bin", bytes(data))
    default_before, full_before = asset_id(path), asset_id(path, full=True)
    data[20 * MIB] ^= 0xFF
    path.write_bytes(bytes(data))
    assert asset_id(path) == default_before  # the documented collision (ADR 0012)
    assert asset_id(path, full=True) != full_before


@pytest.mark.parametrize(
    "case",
    ["first_byte", "last_head_byte", "first_tail_byte", "last_byte", "append_byte"],
)
def test_sensitive_bytes(tmp_path: Path, case: str) -> None:
    data = bytearray(_pattern(SIZE_40MIB))
    path = _write(tmp_path / "pattern.bin", bytes(data))
    before = asset_id(path)
    flip = {
        "first_byte": 0,
        "last_head_byte": 8 * MIB - 1,
        "first_tail_byte": SIZE_40MIB - 8 * MIB,
        "last_byte": SIZE_40MIB - 1,
    }
    if case == "append_byte":
        data.append(0)
    else:
        data[flip[case]] ^= 0xFF
    path.write_bytes(bytes(data))
    assert asset_id(path) != before


def test_sparse_1gib(tmp_path: Path) -> None:
    path = tmp_path / "sparse.bin"
    size = 1 << 30
    with path.open("wb") as f:
        f.truncate(size)
    zeros = bytes(CHUNK)
    expected = hashlib.sha256(size.to_bytes(8, "big") + zeros + zeros).hexdigest()
    assert asset_id(path) == "tsid1:" + expected


@pytest.mark.parametrize("case", ["missing", "directory"])
def test_unreadable_raises_oserror(tmp_path: Path, case: str) -> None:
    path = tmp_path / case
    if case == "directory":
        path.mkdir()
    with pytest.raises(OSError):
        asset_id(path)
