"""Run the GPU test suite and `tapesift doctor` on a real NVIDIA GPU on Modal.

The laptop never runs GPU work (ADR 0008). This ships the working tree to a
Modal container with the requested GPU, runs `uv sync --frozen`, then
`tapesift doctor --json` and `pytest -m gpu`, and saves the doctor report to
docs/verification/doctor-<GPU>.json.

Usage (Modal is a tool, not a project dependency):
    uvx --from modal==1.5.1 modal run scripts/cloud/modal_gpu.py --gpu L4
Cost: about one minute of the chosen GPU, plus image build time on CPU.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import modal

REMOTE = "/repo"
# Modal also imports this file inside the container (as /root/modal_gpu.py), where the
# repo lives at REMOTE instead of two directories up.
ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path(REMOTE)

image = (
    # Not Image.debian_slim(): on this account's builder version it is bullseye, whose
    # security pool now 404s. Debian 13 (trixie) is current.
    modal.Image.from_registry("python:3.12-slim-trixie")
    .apt_install("ffmpeg")
    .pip_install("uv==0.11.27")
    .add_local_dir(
        ROOT,
        REMOTE,
        copy=True,
        ignore=[".venv", ".git", "**/__pycache__", ".ruff_cache", ".pytest_cache", ".claude"],
    )
    .run_commands(f"cd {REMOTE} && uv sync --frozen")
)

app = modal.App("tapesift-gpu", image=image)


@app.function(timeout=900)
def gpu_checks() -> dict[str, str | int]:
    def sh(*cmd: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(cmd), cwd=REMOTE, capture_output=True, text=True, timeout=600, check=False
        )

    doctor = sh("uv", "run", "tapesift", "doctor", "--json")
    smi = sh("nvidia-smi")
    tests = sh("uv", "run", "pytest", "-m", "gpu", "-v", "tests/gpu")
    return {
        "doctor_exit": doctor.returncode,
        "doctor_json": doctor.stdout,
        "doctor_stderr": doctor.stderr[-2000:],
        "nvidia_smi": smi.stdout,
        "pytest_exit": tests.returncode,
        "pytest_output": (tests.stdout + tests.stderr)[-6000:],
    }


@app.local_entrypoint()
def main(gpu: str = "L4") -> None:
    result = gpu_checks.with_options(gpu=gpu).remote()
    print(result["nvidia_smi"])
    print(result["doctor_json"])
    print(result["pytest_output"])
    out = ROOT / "docs" / "verification" / f"doctor-{gpu}.json"
    out.write_text(json.dumps(json.loads(str(result["doctor_json"])), indent=2) + "\n")
    print(f"saved {out.relative_to(ROOT)}")
    if result["doctor_exit"] != 0 or result["pytest_exit"] != 0:
        raise SystemExit(
            f"doctor exit {result['doctor_exit']}, pytest exit {result['pytest_exit']}"
        )
