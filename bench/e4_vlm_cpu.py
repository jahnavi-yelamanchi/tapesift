"""E4 card 6: how fast does TransformersVLM caption on a 4 vCPU CPU box? Runs once on Modal.

The laptop never loads model weights (ADR 0008). This ships the working tree to a Modal
container (cpu=2.0 physical cores = 4 vCPU, 16 GiB, float32), runs the matrix below inside it,
and saves docs/verification/e4-vlm-cpu.json.

Usage (Modal is a tool, not a project dependency):
    uvx --from modal==1.5.1 modal run bench/e4_vlm_cpu.py
Cost: about $0.15 (4 vCPU / 16 GiB is about $0.22/h); the 1 h timeout caps it near $0.25.

Matrix (docs/specs/27-captions.md, card 6): 1 tile at max_batch 1 and 8 on 16 clean.mp4 frames
plus burned_text.mp4's frames (fixed_fps 3.2); 5 tiles (image_longest_edge=1024) at max_batch 8
on 8 burned_text frames. Each config: one warm-up batch, then two timed passes.
"""

from __future__ import annotations

import json
import os
import re
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import modal
except ImportError:  # inside `uv run` in the container the tool is absent; --inner needs none
    modal = None

REMOTE = "/repo"
EVERY_S = 1 / 3.2  # fixed_fps 3.2
WARMUP_LIMIT_S_PER_FRAME = 60.0
PASSES = 2


def _cpu_info() -> dict[str, Any]:
    p = Path("/proc/cpuinfo")
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    m = re.search(r"model name\s*:\s*(.+)", text)
    f = re.search(r"flags\s*:\s*(.+)", text)
    have = set(f.group(1).split()) if f else set()
    return {
        "model_name": m.group(1) if m else "unknown",
        "avx2": "avx2" in have,
        "avx512f": "avx512f" in have,
        "cpu_count": os.cpu_count(),
    }


def _rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux reports KiB


def measure() -> dict[str, Any]:
    """Runs in the container's uv environment: imports torch through tapesift."""
    import torch

    torch.set_num_threads(4)  # before the first torch call

    from tapesift.config import Config
    from tapesift.media.decode import PyAVDecoder
    from tapesift.media.probe import probe
    from tapesift.vision.prompts import CAPTION_V1, ELLIPSIS, PROMPTS, PromptSpec
    from tapesift.vision.transformers_vlm import TransformersVLM

    fixtures = Path(REMOTE) / "tests" / "fixtures"
    burned_text = re.search(
        r'BURNED_TEXT = "(.+)"', (Path(REMOTE) / "scripts" / "make_fixtures.py").read_text("utf-8")
    )
    words = set((burned_text.group(1) if burned_text else "").lower().split())

    def frames(name: str) -> list[Any]:
        asset = probe(fixtures / name)
        return list(PyAVDecoder().iter_frames(asset, EVERY_S, warn=lambda _w: None))

    clean = frames("clean.mp4")[:16]
    burned = frames("burned_text.mp4")
    t_load = time.perf_counter()
    vlm = TransformersVLM(Config())
    load_s = time.perf_counter() - t_load
    base_rss = _rss_mib()

    PROMPTS["bench_5tile"] = PromptSpec(CAPTION_V1.text, 1024, CAPTION_V1.max_new_tokens)
    vlm._chat["bench_5tile"] = vlm._chat["caption_v1"]  # pyright: ignore

    def run(pid: str, pool: list[Any], max_batch: int) -> list[Any]:
        caps: list[Any] = []
        for i in range(0, len(pool), max_batch):
            caps += vlm.caption(pool[i : i + max_batch], pid)
        return caps

    def read_words(caps: list[Any]) -> int:
        seen = {w for c in caps for e in c.media_text for w in e.lower().split()}
        return len(words & seen)

    rows: list[dict[str, Any]] = []
    matrix = [
        ("caption_v1", 1, clean + burned, 1),
        ("caption_v1", 8, clean + burned, 1),
        ("bench_5tile", 8, burned[:8], 5),
    ]
    for pid, max_batch, pool, tiles in matrix:
        row: dict[str, Any] = {"tiles": tiles, "max_batch": max_batch, "frames": len(pool)}
        t0 = time.perf_counter()
        vlm.caption(pool[:max_batch], pid)  # warm-up batch
        warm = (time.perf_counter() - t0) / len(pool[:max_batch])
        if warm > WARMUP_LIMIT_S_PER_FRAME:
            row |= {"skipped": f"warm-up {warm:.1f} s/frame"}
            rows.append(row)
            continue
        per_frame: list[float] = []
        caps: list[Any] = []
        for _ in range(PASSES):
            t0 = time.perf_counter()
            caps = run(pid, pool, max_batch)
            per_frame.append((time.perf_counter() - t0) / len(pool))
        burned_caps = caps[-len(burned[:8]) :] if pid == "bench_5tile" else caps[len(clean) :][:8]
        loops = sum(
            1
            for c in caps
            if c.text.endswith(ELLIPSIS) or any(e.endswith(ELLIPSIS) for e in c.media_text)
        )
        row |= {
            "s_per_frame_median": statistics.median(per_frame),
            "s_per_frame_min": min(per_frame),
            "s_per_frame_max": max(per_frame),
            "warmup_s_per_frame": warm,
            "peak_rss_over_baseline_mib": _rss_mib() - base_rss,  # ru_maxrss: cumulative peak
            "loop_rate": loops / len(caps),  # replies cut by max_new_tokens (or a length cap)
            "burned_words_read": read_words(burned_caps),
            "burned_words_total": len(words),
            "sample_replies": [[c.text, list(c.media_text)] for c in (caps[:2] + burned_caps[:4])],
        }
        rows.append(row)
    return {
        "pin": vlm.id,
        "cpu": _cpu_info(),
        "threads": torch.get_num_threads(),
        "load_s": load_s,
        "baseline_rss_mib": base_rss,
        "rows": rows,
    }


if modal is not None:
    ROOT = Path(__file__).resolve().parents[1] if modal.is_local() else Path(REMOTE)
    image = (
        # Debian 13 (trixie), as scripts/cloud/modal_gpu.py: the default builder's bullseye 404s.
        modal.Image.from_registry("python:3.12-slim-trixie")
        .apt_install("ffmpeg")
        .pip_install("uv==0.11.27")
        .add_local_dir(
            ROOT,
            REMOTE,
            copy=True,
            ignore=[".venv", ".git", "**/__pycache__", ".ruff_cache", ".pytest_cache", ".claude"],
        )
        .run_commands(f"cd {REMOTE} && uv sync --frozen --all-extras")
    )
    cache = modal.Volume.from_name("tapesift-hf-cache", create_if_missing=True)
    app = modal.App("tapesift-e4-vlm-cpu", image=image)

    @app.function(cpu=2.0, memory=16384, timeout=3600, volumes={"/cache": cache})
    def bench() -> dict[str, Any]:
        env = {
            **os.environ,
            "HF_HOME": "/cache",
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "PYTHONPATH": REMOTE,
        }
        t0 = time.perf_counter()
        proc = subprocess.run(
            ["uv", "run", "--frozen", "--all-extras", "python", "bench/e4_vlm_cpu.py", "--inner"],
            cwd=REMOTE,
            env=env,
            capture_output=True,
            text=True,
            timeout=3500,
            check=False,
        )
        cache.commit()
        if proc.returncode != 0:
            raise RuntimeError(f"inner failed ({proc.returncode}): {proc.stderr[-3000:]}")
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        result["wall_s"] = time.perf_counter() - t0
        return result

    @app.local_entrypoint()
    def main() -> None:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30, check=True
        ).stdout.strip()
        result = bench.remote()
        result["git_sha"] = sha
        out = ROOT / "docs" / "verification" / "e4-vlm-cpu.json"
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        sys.stdout.write(f"{result['pin']}\n{result['cpu']}\n")
        for r in result["rows"]:
            sys.stdout.write(json.dumps(r) + "\n")
        sys.stdout.write(f"wall {result['wall_s']:.0f} s; saved {out.relative_to(ROOT)}\n")


if __name__ == "__main__" and "--inner" in sys.argv:
    sys.stdout.write(json.dumps(measure()) + "\n")
