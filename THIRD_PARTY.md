# Third-party components

Every model and runtime library tapesift ships with or downloads, with its license. A model is added here in the same PR that makes it a default.

## Python libraries

| Library | Use | License |
| --- | --- | --- |
| av (PyAV) | Probe and CPU decode | BSD-3-Clause; the FFmpeg bundled in its wheels is LGPL-3.0-or-later |
| numpy | Frame and audio arrays | BSD-3-Clause |

## Models

| Model | Revision | Use | License |
| --- | --- | --- | --- |

## Tools used only to build test fixtures

| Tool | Use | License | Note |
| --- | --- | --- | --- |
| FFmpeg | Test sources and encoders for `scripts/make_fixtures.py` | LGPL-2.1+ / GPL-2.0+ depending on build | Outputs are synthetic and license-free |
| espeak-ng | English speech for `speech.mp4` (ADR 0007) | GPL-3.0 | Generated audio is not covered by the GPL; never a runtime dependency |
