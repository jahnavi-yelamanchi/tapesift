"""Index a few videos on a Modal CPU box and serve the web UI through a public tunnel (spec 40).

Costs money: 2 cores and 8 GiB, about $0.16 per hour. The lead asks the owner before each run.
The function timeout (60 minutes), max_containers=1 and retries=0 cap it near $1. The tunnel URL
is unguessable but public, so use only public or test media. Real models load in the container,
never on the laptop (ADR 0008).

Usage (Modal is a tool, not a project dependency):
    uvx --from modal==1.5.1 modal run scripts/cloud/modal_ui.py
    uvx --from modal==1.5.1 modal run scripts/cloud/modal_ui.py \
        --video-url https://example.org/talk.mp4 --sha256 <hex> --minutes 30
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path

import modal

REMOTE = "/repo"
PORT = 8765
MAX_MINUTES = 30
DEFAULT_PATHS = "tests/fixtures/speech.mp4,tests/fixtures/burned_text.mp4,tests/fixtures/clean.mp4"
# Modal also imports this file inside the container, where the repo lives at REMOTE.
ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path(REMOTE)

image = (
    modal.Image.from_registry("python:3.12-slim-trixie")
    .apt_install("ffmpeg")
    .pip_install("uv==0.11.27")
    .add_local_dir(
        ROOT,
        REMOTE,
        copy=True,
        ignore=[
            ".venv",
            ".git",
            "**/__pycache__",
            ".ruff_cache",
            ".pytest_cache",
            ".claude",
            ".env*",
            "**/.env*",
            "tapesift_index",
            "**/tapesift_index",
            "out",
            "**/*.pem",
            "**/*.key",
            "**/*credential*",
            "**/*secret*",
            "**/id_rsa*",
            "**/id_ed25519*",
            ".netrc",
            ".aws",
            ".ssh",
        ],
    )
    .run_commands(f"cd {REMOTE} && uv sync --frozen --all-extras")
)

app = modal.App("tapesift-ui", image=image)


def _fetch(url: str, sha256: str, dest: Path) -> None:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as src, dest.open("wb") as out:  # noqa: S310
        while chunk := src.read(1 << 20):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != sha256.lower():
        raise SystemExit(f"sha256 mismatch for {url}: got {digest.hexdigest()}")


# timeout is the hard spend cap: index (about 10 min) plus MAX_MINUTES of serving, with slack.
@app.function(cpu=2, memory=8192, timeout=3600, max_containers=1, retries=0)
def serve_ui(paths: list[str], video_url: str, sha256: str, minutes: int) -> None:
    idx = Path("/tmp/idx")  # noqa: S108
    inputs = [str(Path(REMOTE) / p) for p in paths]
    if video_url:
        video = Path("/tmp/video.mp4")  # noqa: S108
        _fetch(video_url, sha256, video)
        inputs.append(str(video))
    config = Path("/tmp/ui.toml")  # noqa: S108
    config.write_text('profile = "cpu"\n\n[asr]\nmodel = "tiny"\n', encoding="utf-8")
    subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "tapesift",
            "index",
            *inputs,
            "--out",
            str(idx),
            "--config",
            str(config),
        ],
        cwd=REMOTE,
        timeout=1800,
        check=True,
    )
    with modal.forward(PORT) as tunnel:
        sys.stdout.write(f"tapesift UI: {tunnel.url}\n")
        sys.stdout.flush()
        server = subprocess.Popen(
            [
                "uv",
                "run",
                "--frozen",
                "tapesift",
                "serve",
                "--out",
                str(idx),
                "--host",
                "0.0.0.0",  # noqa: S104
                "--port",
                str(PORT),
            ],
            cwd=REMOTE,
        )
        try:
            server.wait(timeout=minutes * 60)  # a crashed server ends the run early
        except subprocess.TimeoutExpired:
            pass
        finally:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()


@app.local_entrypoint()
def main(
    paths: str = DEFAULT_PATHS, video_url: str = "", sha256: str = "", minutes: int = MAX_MINUTES
) -> None:
    if not 1 <= minutes <= MAX_MINUTES:
        raise SystemExit(f"--minutes must be 1-{MAX_MINUTES}: the 60-minute timeout caps the spend")
    if bool(video_url) != bool(sha256):
        raise SystemExit("--video-url and --sha256 go together")
    serve_ui.with_options(timeout=(minutes + 30) * 60).remote(
        paths.split(","), video_url, sha256, minutes
    )
