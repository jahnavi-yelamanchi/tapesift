"""tapesift.eval.wer: the normalizer and the word error rate (docs/specs/26-audio.md, row 13).
Pure stdlib code, so there are no backends here."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tapesift.eval.wer import normalize, wer

MANIFEST = Path(__file__).parents[1] / "fixtures" / "manifest.json"
PRINTABLE = st.text(alphabet=[chr(c) for c in range(32, 127)], max_size=60)
WORDS = st.lists(st.sampled_from(["a", "b", "c", "d"]), min_size=1, max_size=8).map(" ".join)

_SMALL = {
    w: i
    for i, w in enumerate(
        [
            *("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
            *("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen"),
            *("seventeen", "eighteen", "nineteen"),
        ]
    )
}
_TENS = {
    w: 10 * i
    for i, w in enumerate(
        ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
    )
    if w
}


def _words_to_int(words: str) -> int:
    """Independent reader of the spec's English numbers (below one million, no "and")."""
    total = current = 0
    for tok in words.split():
        if tok in _SMALL:
            current += _SMALL[tok]
        elif tok in _TENS:
            current += _TENS[tok]
        elif tok == "hundred":
            current *= 100
        elif tok == "thousand":
            total += current * 1000
            current = 0
        else:
            raise AssertionError(f"unexpected token {tok!r} in {words!r}")
    return total + current


@settings(deadline=None)
@given(n=st.integers(min_value=0, max_value=999_999))
def _prop_integers_read_back(n: int) -> None:
    assert _words_to_int(normalize(str(n))) == n
    assert _words_to_int(normalize(f"{n:,}")) == n  # thousands separators


@settings(deadline=None)
@given(text=PRINTABLE)
def _prop_normalize_is_plain_words(text: str) -> None:
    out = normalize(text)
    assert re.fullmatch(r"(?:[a-z]+(?: [a-z]+)*)?", out), out
    assert normalize(out) == out  # idempotent


@settings(deadline=None)
@given(ref=WORDS, hyp=WORDS)
def _prop_wer_is_a_distance(ref: str, hyp: str) -> None:
    n, m = len(ref.split()), len(hyp.split())
    assert wer(ref, ref) == 0.0
    assert wer(ref, "") == 1.0
    assert 0.0 <= wer(ref, hyp) <= max(1.0, m / n)  # edit distance <= max(n, m)
    assert wer(ref, hyp) * n == pytest.approx(wer(hyp, ref) * m)  # Levenshtein is symmetric
    assert wer(ref, hyp + " a") * n <= wer(ref, hyp) * n + 1 + 1e-9  # one insertion costs <= 1


def test_normalize() -> None:
    assert (
        normalize("Revenue grew 12% while costs stayed flat.")
        == "revenue grew twelve percent while costs stayed flat"
    )
    assert normalize("at 9:00") == "at nine"
    assert normalize("1,000") == "one thousand"
    assert normalize("12.5") == "twelve point five"
    assert normalize("2021") == "two thousand twenty one"
    assert normalize("I'm here.") == "i m here"
    # The rest of step 5, and the empty cases.
    assert normalize("0") == "zero"
    assert normalize("105") == "one hundred five"
    assert normalize("0.25") == "zero point two five"
    assert normalize("1000000") == "one zero zero zero zero zero zero"
    assert normalize("") == ""
    assert normalize("...") == ""
    fullwidth = "".join(chr(c) for c in (0xFF21, 0xFF22, 0xFF23, 0x20, 0xFF11, 0xFF12))
    assert normalize(fullwidth) == "abc twelve"  # NFKC folds full-width forms
    _prop_integers_read_back()
    _prop_normalize_is_plain_words()


def test_wer() -> None:
    assert wer("the cat sat", "the cat sat") == 0.0
    assert wer("a b c d", "a x c d") == 0.25
    assert wer("a b c d", "") == 1.0
    assert wer("Hello, World!", "hello world") == 0.0  # compared after normalize()
    with pytest.raises(ValueError):
        wer("...", "anything")
    entries: Any = json.loads(MANIFEST.read_text(encoding="utf-8"))["fixtures"]
    transcript: str = next(e for e in entries if e["name"] == "speech.mp4")["transcript"]
    heard = "The quarterly pricing review starts at 9:00. Revenue grew 12% while costs stayed flat."
    assert wer(transcript, heard) == 0.0
    _prop_wer_is_a_distance()
