import hashlib
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = MANIFEST["fixtures"]

# Every warning code in the messy-data table of docs/spec.md. When E1 adds the
# WarningCode enum to src/, this set should come from there instead.
SPEC_WARNING_CODES = {
    "VFR_DETECTED", "ROTATED", "START_OFFSET", "AV_LENGTH_MISMATCH", "NO_AUDIO",
    "MULTI_AUDIO", "LOW_SPEECH", "PARTIAL_DECODE", "UNSUPPORTED_CODEC", "INTERLACED",
    "CROPPED", "HDR_CONVERTED", "SHORT_CLIP", "DOWNSCALED", "DUPLICATE", "MEDIA_TEXT",
    "MIXED_LANG",
}  # fmt: skip


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["name"] for e in ENTRIES])
def test_fixture_matches_manifest(entry: dict[str, object]) -> None:
    path = FIXTURES / str(entry["name"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], (
        f"{path.name} changed; regenerate with `make fixtures` and commit the manifest"
    )


def test_every_spec_warning_code_has_a_fixture() -> None:
    covered = {code for e in ENTRIES for code in e["warning_codes"]}
    assert covered == SPEC_WARNING_CODES


def test_rows_without_a_code_have_fixtures() -> None:
    # "Very long file" and "Unicode or spaces in paths" have no warning code.
    names = {e["name"] for e in ENTRIES}
    assert {"long_3h.mp4", "réunion 01.mp4", "clean.mp4", "speech.mp4"} <= names


def test_fixtures_stay_under_five_megabytes() -> None:
    assert sum(p.stat().st_size for p in FIXTURES.iterdir()) < 5 * 1024 * 1024


def test_no_unlisted_files() -> None:
    on_disk = {p.name for p in FIXTURES.iterdir()} - {"manifest.json"}
    assert on_disk == {e["name"] for e in ENTRIES}


def test_speech_fixtures_carry_reference_transcripts() -> None:
    by_name = {e["name"]: e for e in ENTRIES}
    assert "pricing" in by_name["speech.mp4"]["transcript"]
    assert by_name["mixed_lang.mp4"]["transcript"]
