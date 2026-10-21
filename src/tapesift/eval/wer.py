"""Word error rate and its normalizer (owner Q8 A). Pure stdlib; V2 reuses both."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

_ONES: Final = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
)  # fmt: skip
_TENS: Final = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)


def _below_thousand(n: int) -> list[str]:
    words: list[str] = []
    if n >= 100:
        words += [_ONES[n // 100], "hundred"]
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
        if n:
            words.append(_ONES[n])
    elif n or not words:
        words.append(_ONES[n])
    return words


def _int_words(digits: str) -> list[str]:
    n = int(digits)
    if n >= 1_000_000:
        return [_ONES[int(d)] for d in digits]
    if n >= 1000:
        words = [*_below_thousand(n // 1000), "thousand"]
        return words + (_below_thousand(n % 1000) if n % 1000 else [])
    return _below_thousand(n)


def _number(m: re.Match[str]) -> str:
    whole, _, frac = m.group(0).partition(".")
    words = _int_words(whole)
    if frac:
        words += ["point", *(_ONES[int(d)] for d in frac)]
    return " " + " ".join(words) + " "


def normalize(text: str) -> str:
    """1. unicodedata.normalize("NFKC", text).lower()
    2. thousands separators dropped: re.sub(r"(?<=\\d),(?=\\d{3}\\b)", "", t)
    3. ":00" after a number dropped: re.sub(r"(\\d):00\\b", r"\\1", t)
    4. "%" -> " percent "
    5. each r"\\d+(?:\\.\\d+)?" -> English words: integers below one million without "and"
       (0 "zero", 105 "one hundred five", 2021 "two thousand twenty one"), longer integers
       digit by digit; a fraction is "point" plus one word per digit
    6. re.sub(r"[\\W_]+", " ", t).strip()"""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"(\d):00\b", r"\1", t)
    t = t.replace("%", " percent ")
    t = re.sub(r"\d+(?:\.\d+)?", _number, t)
    return re.sub(r"[\W_]+", " ", t).strip()


def wer(reference: str, hypothesis: str) -> float:
    """(S + D + I) / reference word count, by word-level Levenshtein on normalize()d text split
    on spaces. ValueError if the normalized reference is empty."""
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    if not ref:
        raise ValueError("reference has no words after normalization")
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref)
