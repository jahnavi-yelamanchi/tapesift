# Q1: install timing, lean vs torch (2026-10-19)

Question: does a tool env with transformers + torch (VLM path) plus the lean v0.1 set install in under 2 minutes on GitHub Actions ubuntu-latest and macos-latest? If Linux > 2 min, choose a `tapesift[vision]` extra. Owner approved ("measure, then decide").

## Setup
- Workflow: `.github/workflows/exp-q1-install-timing.yml` (branch `exp/q1-install-timing`, not for main).
- Python 3.12, `uv pip install` into a fresh venv, `UV_NO_CACHE=1`, no setup-uv caching, so every wheel is downloaded. Timed with `date +%s` around the install only (venv creation excluded).
- lean: `faster-whisper==1.2.1 lancedb==0.40.* pydantic==2.14.* av>=19.0.1 numpy>=2.5.4 typer onnxruntime tokenizers`. All pins resolved first try.
- full: lean + `transformers>=5,<6` + `torch` (default PyPI index).
- Not measured: `uv tool install` (tapesift is not on PyPI; the venv install is the same resolution and download work).
- Single run per OS, so no variance estimate. Runner network speed varies.

## Results

| OS | lean (s) | full (s) | lean venv | full venv |
|---|---|---|---|---|
| ubuntu-latest | 4 | 33 | 778 MB | 6124 MB |
| macos-latest | 3 | 10 | 479 MB | 1116 MB |

Bar: 120 s. Linux full is 33 s (27% of the bar); macOS full is 10 s.

Linux full venv breakdown (MB): nvidia 3196, torch 1120, triton 894, lancedb 178, pyarrow 162, av.libs 101, ctranslate2(+libs) 137, onnxruntime 63, transformers 57. The CUDA wheels (nvidia-* and triton) are about 4 GB of the 6.1 GB. macOS torch is 532 MB, no CUDA.

## Resolved versions (identical on both OS unless noted)
torch 2.14.1, transformers 5.20.2, nvidia-cublas 13.1.1.3 and nvidia-cuda-runtime 13.0.96 (Linux only), faster-whisper 1.2.1, lancedb 0.40.0, pydantic 2.14.1, av 19.0.1, numpy 2.5.4, onnxruntime 1.31.0, tokenizers 0.23.3, typer 0.27.3, pyarrow 26.0.0, ctranslate2 4.8.3, huggingface-hub 2.2.0.

Run: https://github.com/jahnavi-yelamanchi/tapesift/actions/runs/39347647667 (both jobs green; full tables in the job summaries).

## Conclusion
The 2-minute bar holds on both OSes with wide margin. By the owner's stated rule, the `tapesift[vision]` extra is not triggered on time grounds.

## Recommendation
A (torch in base), on the stated criterion. Caveat for the owner: this was a time bar only. Linux users get a 6.1 GB env (about 8x lean) because default PyPI torch pulls CUDA, which hurts disk, Docker image size and cold pulls on slow networks, none of which this experiment measured. If that matters, B (`tapesift[vision]`) remains cheap to choose later only if torch is not yet imported by base code paths; moving it out after users depend on it is a breaking change. Option A-prime (torch in base but pinned to the CPU index) would shrink Linux to roughly 1 GB but changes dependency sourcing, which is a separate T2 card.
