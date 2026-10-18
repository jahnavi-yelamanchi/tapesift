# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- `tapesift --version` and the package skeleton (`uvx --from . tapesift --version`).
- 25 synthetic fixtures covering every warning code in the spec, built by `make fixtures` (2.8 MB).
- `tapesift doctor [--json]`: reports Python, FFmpeg, CUDA, GPUs, NVDEC and free disk, picks the `cpu`, `gpu` or `server` profile, lists every network call tapesift can make. Exits 3 on an environment problem.
- Shared media types, the `UNREADABLE` warning code and the `Decoder` protocol; numpy and PyAV become dependencies.
- `probe` reads media metadata into `AssetInfo` with warning codes; asset IDs are `tsid1:` (size, first and last 8 MiB) or, opt-in, `sha256:` of the whole file.
- CPU decode with PyAV: PTS-timed, upright, downscaled frames and 16 kHz mono audio chunks (#6).
- Smoke test that runs `probe` then `PyAVDecoder` over every fixture and checks decode honors probe's rotation, duration, default audio track and warning codes (#12).

### Changed
- **Breaking:** Python 3.12 or newer is required; 3.11 is no longer supported (ADR 0011).
