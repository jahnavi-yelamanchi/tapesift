# Third-party components

Every model and runtime library tapesift ships with or downloads, with its license. A model is added here in the same PR that makes it a default.

## Python libraries

| Library | Use | License |
| --- | --- | --- |

## Models

| Model | Revision | Use | License |
| --- | --- | --- | --- |

## Tools used only to build test fixtures

| Tool | Use | License | Note |
| --- | --- | --- | --- |
| FFmpeg | Test sources and encoders for `scripts/make_fixtures.py` | LGPL-2.1+ / GPL-2.0+ depending on build | Outputs are synthetic and license-free |
| espeak-ng | Speech for `speech.mp4` and `mixed_lang.mp4` (ADR 0007) | GPL-3.0 | Generated audio is not covered by the GPL; never a runtime dependency |
