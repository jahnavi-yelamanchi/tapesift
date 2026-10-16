# 0008. The laptop only builds code; models, datasets and training run in the cloud

Date: 2026-10-16   Status: accepted (your constraint; replaces plan default D2)   Tier: T2

## Context
The plan's default D2 ran the `cpu` profile with tiny models on the laptop. Your constraint: no local dataset downloads and no local training. The laptop has 67 GB free.

## Options
1. Laptop runs code, unit tests and fixture smoke tests with fake backends; anything that loads real weights or datasets runs in the cloud. Pros: honors the constraint; tests stay fast. Cons: real-model bugs surface only in CI or cloud runs.
2. Allow tiny model weights locally (under 1 GB). Cons: violates the constraint.

## Decision
Option 1, with one place for each kind of work:
- **GitHub Actions**: unit and fixture smoke tests on Linux and macOS; later the tiny-model CPU smoke run (weights cached in CI, not on the laptop).
- **Modal**: GPU tests (`@pytest.mark.gpu`), `doctor` on real GPUs, benchmarks (`bench/`), short training jobs. Per-second billing, scripted from the repo.
- **Vast.ai**: long training runs (GRPO, self-training rounds) where hourly price matters more than convenience.
- **Colab**: interactive exploration notebooks only; nothing that a published number depends on.
- **Hugging Face Hub**: datasets, eval suites and trained adapters, pinned by revision.

## Consequences
Every backend gets a fake for local tests. Every published number comes from a script in `bench/` or `evals/` that runs on Modal or Vast, never from a notebook.

## Revisit if
Cloud round trips slow the inner loop enough that a single tiny-model local smoke test would save hours a week.
