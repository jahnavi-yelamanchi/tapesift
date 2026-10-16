# 0002. tapesift starts and stops vLLM itself on NVIDIA GPUs

Date: 2026-10-13   Status: accepted   Tier: T3

## Context
VLM captioning is the most expensive stage. vLLM gives the best throughput on NVIDIA, but its pinned torch clashes with other packages, and asking users to run a server breaks the one-command promise.

## Options
1. Users run vLLM themselves and set `vlm.endpoint`. Pros: simplest for us. Cons: breaks `uvx tapesift index` on a fresh box.
2. tapesift runs `uvx vllm serve <model>` in its own isolated environment, health-checks it, batches requests, and stops it at the end; `vlm.endpoint` still accepts an existing server. Pros: one command, no torch clash. Cons: large one-time download on first GPU run.
3. Bundle vLLM as a Python dependency. Cons: torch version conflicts for every user.

## Decision
Option 2. CPU and Mac run small models in-process. `tapesift models pull` pre-downloads. The `cuda` Docker image ships vLLM inside.

## Consequences
We own a subprocess lifecycle (timeouts, cleanup on crash, port selection). Air-gapped installs need `models pull` first.

## Revisit if
Managed startup fails on common setups, or the one-time download blocks first runs.
