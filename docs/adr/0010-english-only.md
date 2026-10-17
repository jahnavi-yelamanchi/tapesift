# 0010. English only in v1.0

Date: 2026-10-16   Status: accepted (owner's call)   Tier: T3

## Context
The plan treated Telugu-English and Hindi-English code-switched speech as a differentiator: a `MIXED_LANG` warning code and fixture, a 30-minute code-switched eval suite, and code-switched WER in the fairness report. The owner needs English only.

## Options
A. Keep code-switching as planned. Cons: a recorded dataset, a fixture and an eval suite the owner does not need.
B. English only; other languages best effort. Pros: smaller eval surface; every published number is about English. Cons: drops one differentiator.

## Decision
B. Removed: the `MIXED_LANG` warning code, its fixture, the code-switched eval suite, and code-switched WER from V2 and Y4. Kept: Whisper still transcribes whatever it hears, and each utterance still records its detected language (output schema unchanged), so non-English footage degrades instead of failing. Nothing non-English is evaluated, tuned or claimed. The multi-audio fixture now has two English tracks (main and commentary).

## Consequences
Every accuracy and fairness number is about English. Accent fairness (Common Voice English accents) stays.

## Revisit if
A buyer conversation or pilot needs another language.
