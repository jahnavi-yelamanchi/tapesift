"""`tapesift doctor`: report the machine and pick a hardware profile.

Probing is separated from the command so tests can hand in a fake `Probes`
and check every machine shape (laptop, consumer GPU, datacenter GPU, broken
driver) without owning one.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import cast

NVIDIA_SMI_TIMEOUT_S = 10.0
MIN_GPU_VRAM_MIB = 8 * 1024
MIN_FREE_DISK_GIB = 2.0

# Datacenter parts get the `server` profile: batched ASR across files and a managed vLLM.
# Matched as whole words in the nvidia-smi name, e.g. "NVIDIA L4", "NVIDIA A100-SXM4-80GB".
SERVER_GPUS = ("L4", "L40", "L40S", "A10", "A10G", "A30", "A40", "A100", "H100", "H200",
               "GH200", "B100", "B200", "RTX 6000 Ada")  # fmt: skip

# Every network call tapesift can make (Y3: privacy by default). Nothing else is contacted.
NETWORK_CALLS = (
    "huggingface.co: model weights, on first use or `tapesift models pull`",
    "pypi.org: the vLLM runtime via `uvx vllm`, NVIDIA profiles only, on first use",
)


class Profile(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    SERVER = "server"


@dataclass(frozen=True)
class Gpu:
    name: str
    vram_mib: int
    driver: str
    nvdec: bool


@dataclass(frozen=True)
class Report:
    tapesift: str
    python: str
    platform: str
    machine: str
    pyav: str | None
    ffmpeg: str | None
    torchcodec: str | None
    cuda: str | None
    gpus: list[Gpu]
    disk_free_gib: float | None
    disk_path: str
    profile: Profile
    profile_reason: str
    decode: str
    problems: list[str] = field(default_factory=list[str])
    notes: list[str] = field(default_factory=list[str])
    network_calls: list[str] = field(default_factory=lambda: list(NETWORK_CALLS))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


Runner = Callable[[list[str], float], str]
"""Runs a command with a timeout and returns stdout; raises OSError or
subprocess.SubprocessError (including TimeoutExpired) on failure."""


def run_command(cmd: list[str], timeout_s: float) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout_s).stdout


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _pyav_ffmpeg() -> str | None:
    # Imported by name: PyAV is optional until the media stages (E2) depend on it.
    try:
        av = importlib.import_module("av")
    except ImportError:
        return None
    versions = cast(dict[str, tuple[int, int, int]], getattr(av, "library_versions", {}))
    major, minor, micro = versions.get("libavformat", (0, 0, 0))
    return f"libavformat {major}.{minor}.{micro} (bundled with PyAV)"


@dataclass(frozen=True)
class Probes:
    """Everything doctor reads from the machine. Tests replace these."""

    run: Runner = run_command
    which: Callable[[str], str | None] = shutil.which
    version_of: Callable[[str], str | None] = package_version
    disk_free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free
    pyav_ffmpeg: Callable[[], str | None] = _pyav_ffmpeg
    python: str = platform.python_version()
    system: str = f"{platform.system()} {platform.release()}"
    machine: str = platform.machine()


def _system_ffmpeg(probes: Probes) -> str | None:
    if probes.which("ffmpeg") is None:
        return None
    try:
        first = probes.run(["ffmpeg", "-hide_banner", "-version"], NVIDIA_SMI_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r"ffmpeg version (\S+)", first)
    return f"{match.group(1)} (system)" if match else None


def parse_gpus(csv: str) -> list[Gpu]:
    """Parse `nvidia-smi --query-gpu=name,memory.total,driver_version,utilization.decoder
    --format=csv,noheader,nounits`. A decoder utilization of "[N/A]" or "[Not Supported]"
    means the GPU has no NVDEC engine."""
    gpus: list[Gpu] = []
    for line in csv.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            continue
        name, vram, driver, decoder = parts
        try:
            vram_mib = int(float(vram))
        except ValueError:
            vram_mib = 0
        gpus.append(Gpu(name, vram_mib, driver, nvdec=not decoder.startswith("[")))
    return gpus


def parse_cuda_version(smi_banner: str) -> str | None:
    # Drivers before 600 print "CUDA Version: 12.4"; 610+ print "CUDA UMD Version: 13.3".
    match = re.search(r"CUDA (?:UMD )?Version:\s*([\d.]+)", smi_banner)
    return match.group(1) if match else None


def is_server_gpu(name: str) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(m)}(?![\w])", name) for m in SERVER_GPUS)


def pick_profile(gpus: list[Gpu]) -> tuple[Profile, str]:
    if not gpus:
        return Profile.CPU, "no NVIDIA GPU found"
    best = max(gpus, key=lambda g: g.vram_mib)
    if is_server_gpu(best.name):
        return Profile.SERVER, f"datacenter GPU: {best.name}"
    if best.vram_mib >= MIN_GPU_VRAM_MIB:
        return Profile.GPU, f"{best.name} with {best.vram_mib // 1024} GiB VRAM"
    return Profile.CPU, f"{best.name} has {best.vram_mib} MiB VRAM; the gpu profile needs 8 GiB"


def diagnose(probes: Probes, disk_path: Path, tapesift_version: str) -> Report:
    problems: list[str] = []
    notes: list[str] = []

    gpus: list[Gpu] = []
    cuda: str | None = None
    if probes.which("nvidia-smi") is not None:
        query = [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version,utilization.decoder",
            "--format=csv,noheader,nounits",
        ]
        try:
            gpus = parse_gpus(probes.run(query, NVIDIA_SMI_TIMEOUT_S))
            cuda = parse_cuda_version(probes.run(["nvidia-smi"], NVIDIA_SMI_TIMEOUT_S))
        except subprocess.TimeoutExpired:
            problems.append("nvidia-smi timed out; the NVIDIA driver may be hung")
        except (OSError, subprocess.SubprocessError) as exc:
            problems.append(f"nvidia-smi failed ({type(exc).__name__}); check the NVIDIA driver")

    profile, reason = pick_profile(gpus)

    pyav = probes.version_of("av")
    ffmpeg = probes.pyav_ffmpeg() if pyav else _system_ffmpeg(probes)
    torchcodec = probes.version_of("torchcodec")
    has_nvdec = any(g.nvdec for g in gpus)
    if has_nvdec and torchcodec:
        decode = "nvdec (torchcodec)"
    elif pyav:
        decode = "cpu (PyAV)"
    else:
        decode = "unavailable"
        notes.append("PyAV is not installed; decoding arrives with the media stages (E2)")
    if has_nvdec and not torchcodec:
        notes.append('NVDEC present; install "tapesift[gpu]" for GPU decode')
    if probes.machine in ("arm64", "aarch64") and probes.system.startswith("Darwin"):
        notes.append("Apple Silicon: cpu profile with in-process small models")

    free_gib: float | None
    try:
        free_gib = round(probes.disk_free_bytes(disk_path) / 1024**3, 1)
    except OSError as exc:
        free_gib = None
        problems.append(f"cannot read free space at {disk_path}: {exc.strerror}")
    if free_gib is not None and free_gib < MIN_FREE_DISK_GIB:
        problems.append(
            f"only {free_gib} GiB free at {disk_path}; models need {MIN_FREE_DISK_GIB} GiB or more"
        )

    return Report(
        tapesift=tapesift_version,
        python=probes.python,
        platform=probes.system,
        machine=probes.machine,
        pyav=pyav,
        ffmpeg=ffmpeg,
        torchcodec=torchcodec,
        cuda=cuda,
        gpus=gpus,
        disk_free_gib=free_gib,
        disk_path=str(disk_path),
        profile=profile,
        profile_reason=reason,
        decode=decode,
        problems=problems,
        notes=notes,
    )


def render(report: Report) -> str:
    def missing(value: str | None) -> str:
        return value or "not installed"

    lines = [
        f"tapesift     {report.tapesift}",
        f"python       {report.python} on {report.platform} ({report.machine})",
        f"pyav         {missing(report.pyav)}",
        f"ffmpeg       {report.ffmpeg or 'not found'}",
        f"torchcodec   {missing(report.torchcodec)}",
        f"cuda         {report.cuda or 'no NVIDIA driver'}",
    ]
    if report.gpus:
        for i, gpu in enumerate(report.gpus):
            nvdec = "NVDEC" if gpu.nvdec else "no NVDEC"
            lines.append(
                f"gpu {i}        {gpu.name}, {gpu.vram_mib / 1024:.0f} GiB, "
                f"driver {gpu.driver}, {nvdec}"
            )
    else:
        lines.append("gpu          none")
    lines += [
        f"disk free    {report.disk_free_gib} GiB at {report.disk_path}"
        if report.disk_free_gib is not None
        else f"disk free    unknown at {report.disk_path}",
        f"decode       {report.decode}",
        f"profile      {report.profile.value}  ({report.profile_reason})",
    ]
    lines += [f"note         {n}" for n in report.notes]
    lines += [f"PROBLEM      {p}" for p in report.problems]
    lines.append("network      only these, never telemetry:")
    lines += [f"               {c}" for c in report.network_calls]
    return "\n".join(lines)
