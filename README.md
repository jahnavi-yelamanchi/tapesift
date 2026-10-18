# tapesift

Self-hosted engine that turns hours of video and audio into searchable, timestamped data, at the lowest cost per hour.

> Status: pre-alpha. Phase 0 (setup) is done; probe and CPU decode exist. Not usable for indexing yet. The build plan lives in [docs/spec.md](docs/spec.md).

## What it will do

- Index a folder of video or audio on your own machine: laptop CPU, consumer NVIDIA GPU, or datacenter GPU.
- Transcribe speech with word timestamps, split shots, drop near-duplicate frames, caption only the frames that add something.
- Answer "find the moment where X is said or shown" from a CLI, a Python API, an HTTP API or an MCP server.
- Report its own throughput (video-hours per GPU-hour) and cost ($ per video-hour) with `tapesift bench`.

## Acceptable use

tapesift does **not** do face recognition, person identification, or tracking of named individuals, and never will. Pull requests adding them will be closed.

## Non-goals for v1.0

- No face recognition or person identification. Ever.
- No hosted service.
- No video generation or editing.
- No training of base models; only post-training of small open models.
- No real-time streaming; batch first.
- No Windows-native support; WSL2 is best effort.
- English only. Other languages are transcribed best effort, never evaluated.

## Privacy

No telemetry. The only network calls are model downloads, and `tapesift doctor` lists them.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/). ffmpeg and espeak-ng are needed only to regenerate fixtures (`make fixtures`).

```bash
gh repo clone jahnavi-yelamanchi/tapesift   # private for now
cd tapesift
uv sync --all-extras
make check
```

See [AGENTS.md](AGENTS.md) for the rules every contributor (human or agent) follows, and [docs/guides/setup.md](docs/guides/setup.md) for the full dev and cloud-compute setup.

## License

Apache-2.0. Third-party models and libraries are listed in [THIRD_PARTY.md](THIRD_PARTY.md).
