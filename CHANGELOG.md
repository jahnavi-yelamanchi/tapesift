# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- `tapesift --version` and the package skeleton (`uvx --from . tapesift --version`).
- 23 synthetic messy-data fixtures covering every warning code in the spec, built by `make fixtures` (2.8 MB).
- `tapesift doctor [--json]`: reports Python, FFmpeg, CUDA, GPUs, NVDEC and free disk, picks the `cpu`, `gpu` or `server` profile, lists every network call tapesift can make. Exits 3 on an environment problem.
