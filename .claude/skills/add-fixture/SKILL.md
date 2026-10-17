---
name: add-fixture
description: How to add a messy-data test fixture to tapesift. Use when a new edge case in media handling needs a file to test against.
---
# Add a fixture

1. Add one entry to `FIXTURES` in `scripts/make_fixtures.py`: file name, the ffmpeg (or espeak-ng) arguments, the warning code it should trigger, and what it exercises.
2. Use only FFmpeg test sources (`testsrc2`, `smptehdbars`, `color`, `sine`, `anoisesrc`, `anullsrc`) or espeak-ng for speech. Never real footage.
3. Keep it tiny: low resolution, a few seconds, low bitrate, unless the case is about size or length.
4. `make fixtures`, then check the total stays under 5 MB (the script fails if not).
5. Add an assertion for its properties to `tests/unit/test_fixtures.py`.
6. Commit the fixture, the updated `tests/fixtures/manifest.json` and the script change together.
