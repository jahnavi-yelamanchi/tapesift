# Third-party components

Every model and runtime library tapesift ships with or downloads, with its license. A model is added here in the same PR that makes it a default.

## Python libraries

| Library | Use | License |
| --- | --- | --- |
| av (PyAV) | Probe and CPU decode | BSD-3-Clause; the FFmpeg bundled in its wheels is LGPL-3.0-or-later |
| numpy | Frame and audio arrays | BSD-3-Clause |
| faster-whisper | ASR; brings CTranslate2 (MIT) | MIT |
| onnxruntime | Silero VAD and the text embedder | MIT |
| tokenizers | Text embedder tokenization | Apache-2.0 |
| huggingface-hub | Fetches pinned model files (tapesift.hub) | Apache-2.0 |
| lancedb | Search store; brings pyarrow (Apache-2.0) | Apache-2.0 |
| pydantic | Config validation | MIT |
| rich | Terminal output (also a typer dependency; declared directly, owner 2026-10-20) | MIT |
| transformers | VLM captions, in-process; pinned ==5.20.2 (vision extra) | Apache-2.0 |
| torch | VLM runtime (vision extra) | BSD-3-Clause; PyPI expression: Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT |
| pillow | Image backend for the SmolVLM processor (vision extra) | MIT-CMU |
| fastapi | Local web UI server (serve extra); brings starlette (BSD-3-Clause), opentelemetry-api (Apache-2.0, API only, no exporter) | MIT |
| uvicorn | HTTP server for the web UI (serve extra) | BSD-3-Clause |

## Models

| Model | Revision | Use | License |
| --- | --- | --- | --- |
| Systran/faster-whisper-small | 536b0662742c02347bc0e980a01041f333bce120 | ASR, every profile in v0.1 (CTranslate2) | MIT |
| Systran/faster-whisper-tiny | d90ca5fe260221311c53c58e660288d3deb8d356 | ASR for fast CI runs (CTranslate2) | MIT |
| HuggingFaceTB/SmolVLM2-256M-Video-Instruct | 067788b187b95ebe7b2e040b3e4299e342e5b8fd | Frame captions, vision extra (safetensors) | Apache-2.0 |
| BAAI/bge-small-en-v1.5 (onnx/model.onnx and tokenizer.json only) | 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a | Text embeddings for search (ONNX) | MIT |
| Silero VAD v6 (silero_vad_v6.onnx, bundled in faster-whisper) | faster-whisper 1.2.1 | Voice activity detection | MIT |

## Tools used only to build test fixtures

| Tool | Use | License | Note |
| --- | --- | --- | --- |
| FFmpeg | Test sources and encoders for `scripts/make_fixtures.py` | LGPL-2.1+ / GPL-2.0+ depending on build | Outputs are synthetic and license-free |
| espeak-ng | English speech for `speech.mp4` (ADR 0007) | GPL-3.0 | Generated audio is not covered by the GPL; never a runtime dependency |

## Media

| Asset | Use | License | Note |
| --- | --- | --- | --- |
| "Humans define Wikipedia's values and ethics" by Lane Rasberry (Commons user Bluerasberry), [source](https://commons.wikimedia.org/wiki/File:Humans_define_Wikipedia%27s_values_and_ethics.webm) | Frames shown in `docs/media/demo.gif` and `demo.mp4` (README demo) | CC BY 4.0 | Frames unmodified, inside a screen recording of the tapesift UI |
