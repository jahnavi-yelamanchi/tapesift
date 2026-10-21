import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tapesift.cli
from tapesift.cli import ExitCode, app
from tapesift.cli.doctor import (
    Gpu,
    Probes,
    Profile,
    diagnose,
    is_server_gpu,
    parse_cuda_version,
    parse_gpus,
    pick_profile,
    render,
)

SMI_BANNER = """
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.54.15              Driver Version: 550.54.15      CUDA Version: 12.4     |
+-----------------------------------------------------------------------------------------+
"""
GIB = 1024**3


def fake_probes(
    smi_csv: str | None = None,
    *,
    smi_error: Exception | None = None,
    packages: dict[str, str] | None = None,
    free_bytes: int = 100 * GIB,
    system: str = "Linux 6.8.0",
    machine: str = "x86_64",
) -> Probes:
    """A machine described by what nvidia-smi prints and which packages are installed."""
    installed = packages or {}

    def run(cmd: list[str], timeout_s: float) -> str:
        assert timeout_s > 0, "every subprocess call needs a timeout"
        if cmd[0] == "ffmpeg":
            return "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023\n"
        if smi_error is not None:
            raise smi_error
        assert smi_csv is not None
        return smi_csv if any(a.startswith("--query-gpu") for a in cmd) else SMI_BANNER

    def which(name: str) -> str | None:
        if name == "nvidia-smi":
            return "/usr/bin/nvidia-smi" if smi_csv is not None or smi_error else None
        return f"/usr/bin/{name}"

    return Probes(
        run=run,
        which=which,
        version_of=installed.get,
        disk_free_bytes=lambda _: free_bytes,
        pyav_ffmpeg=lambda: "libavformat 61.7.100 (bundled with PyAV)",
        python="3.12.3",
        system=system,
        machine=machine,
    )


# ---- parsing --------------------------------------------------------------


def test_parse_gpus_reads_every_line_and_nvdec() -> None:
    csv = "NVIDIA A100-SXM4-80GB, 81920, 550.54.15, 0\nNVIDIA A100-SXM4-80GB, 81920, 550.54.15, 3\n"
    assert parse_gpus(csv) == [Gpu("NVIDIA A100-SXM4-80GB", 81920, "550.54.15", nvdec=True)] * 2


@pytest.mark.parametrize("decoder", ["[N/A]", "[Not Supported]"])
def test_parse_gpus_marks_missing_nvdec(decoder: str) -> None:
    assert parse_gpus(f"Some GPU, 8192, 535.0, {decoder}")[0].nvdec is False


def test_parse_gpus_skips_malformed_lines() -> None:
    assert parse_gpus("garbage\n\nNVIDIA L4, 23034, 550.54.15, 0\n") == [
        Gpu("NVIDIA L4", 23034, "550.54.15", nvdec=True)
    ]


def test_parse_cuda_version() -> None:
    assert parse_cuda_version(SMI_BANNER) == "12.4"
    assert parse_cuda_version("no banner") is None


def test_parse_cuda_version_from_610_driver_banner() -> None:
    # Verbatim from a Modal L4, Oct 2026 (docs/verification/doctor-L4.json).
    banner = "| NVIDIA-SMI 610.57.04   KMD Version: 610.57.04   CUDA UMD Version: 13.3     |"
    assert parse_cuda_version(banner) == "13.3"


@pytest.mark.parametrize(
    ("name", "server"),
    [
        ("NVIDIA L4", True),
        ("NVIDIA L40S", True),
        ("NVIDIA A10G", True),
        ("NVIDIA A100-SXM4-80GB", True),
        ("NVIDIA A100 80GB PCIe", True),
        ("NVIDIA H100 80GB HBM3", True),
        ("NVIDIA RTX 6000 Ada Generation", True),
        ("NVIDIA GeForce RTX 4090", False),
        ("NVIDIA GeForce RTX 3050 Laptop GPU", False),
        ("Tesla T4", False),
        ("NVIDIA A1000", False),
    ],
)
def test_is_server_gpu(name: str, server: bool) -> None:
    assert is_server_gpu(name) is server


# ---- profile choice -------------------------------------------------------


def test_profile_cpu_without_gpu() -> None:
    assert pick_profile([]) == (Profile.CPU, "no NVIDIA GPU found")


def test_profile_gpu_needs_eight_gib() -> None:
    small = Gpu("NVIDIA GeForce RTX 3050 Laptop GPU", 4096, "550", nvdec=True)
    big = Gpu("NVIDIA GeForce RTX 4090", 24564, "550", nvdec=True)
    assert pick_profile([small])[0] is Profile.CPU
    assert pick_profile([big])[0] is Profile.GPU
    assert pick_profile([small, big])[0] is Profile.GPU


def test_profile_server_for_datacenter_gpu() -> None:
    assert pick_profile([Gpu("NVIDIA L4", 23034, "550", nvdec=True)])[0] is Profile.SERVER


# ---- whole machines -------------------------------------------------------


def test_laptop_without_pyav() -> None:
    report = diagnose(
        fake_probes(system="Darwin 25.6.0", machine="arm64"), Path("/home/me"), "0.1.0"
    )
    assert report.profile is Profile.CPU
    assert report.gpus == [] and report.cuda is None
    assert report.decode == "unavailable"
    assert report.ffmpeg == "6.1.1-3ubuntu5 (system)"
    assert report.problems == []
    assert any("Apple Silicon" in n for n in report.notes)


def test_l4_box_with_gpu_extra() -> None:
    probes = fake_probes(
        "NVIDIA L4, 23034, 550.54.15, 0", packages={"av": "16.0.1", "torchcodec": "0.9.0"}
    )
    report = diagnose(probes, Path("/data"), "0.1.0")
    assert report.profile is Profile.SERVER
    assert report.cuda == "12.4"
    assert report.decode == "nvdec (torchcodec)"
    assert report.ffmpeg == "libavformat 61.7.100 (bundled with PyAV)"


def test_gpu_without_torchcodec_decodes_on_cpu_and_says_how_to_fix() -> None:
    probes = fake_probes("NVIDIA GeForce RTX 4090, 24564, 550.54.15, 0", packages={"av": "16"})
    report = diagnose(probes, Path("/data"), "0.1.0")
    assert report.profile is Profile.GPU
    assert report.decode == "cpu (PyAV)"
    assert any("tapesift[gpu]" in n for n in report.notes)


def test_hung_driver_is_a_problem_not_a_crash() -> None:
    probes = fake_probes(smi_error=subprocess.TimeoutExpired(["nvidia-smi"], 10))
    report = diagnose(probes, Path("/data"), "0.1.0")
    assert report.profile is Profile.CPU
    assert report.problems == ["nvidia-smi timed out; the NVIDIA driver may be hung"]


def test_broken_driver_is_a_problem() -> None:
    probes = fake_probes(smi_error=subprocess.CalledProcessError(9, ["nvidia-smi"]))
    report = diagnose(probes, Path("/data"), "0.1.0")
    assert report.problems and "nvidia-smi failed" in report.problems[0]


def test_low_disk_is_a_problem() -> None:
    report = diagnose(fake_probes(free_bytes=GIB), Path("/data"), "0.1.0")
    assert report.disk_free_gib == 1.0
    assert report.problems and "1.0 GiB free" in report.problems[0]


def test_unreadable_disk_is_a_problem() -> None:
    def boom(_: Path) -> int:
        raise PermissionError(13, "Permission denied")

    probes = replace(fake_probes(), disk_free_bytes=boom)
    report = diagnose(probes, Path("/root"), "0.1.0")
    assert report.disk_free_gib is None
    assert report.problems == ["cannot read free space at /root: Permission denied"]


def test_render_lists_network_calls_and_problems() -> None:
    probes = fake_probes(smi_error=subprocess.TimeoutExpired(["nvidia-smi"], 10))
    text = render(diagnose(probes, Path("/data"), "0.1.0"))
    assert "huggingface.co" in text
    assert "PROBLEM      nvidia-smi timed out" in text


# ---- CLI ------------------------------------------------------------------

runner = CliRunner()


def test_cli_json_output_and_ok_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tapesift.cli, "Probes", lambda: fake_probes("NVIDIA L4, 23034, 550, 0"))
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == ExitCode.OK
    data = json.loads(result.stdout)
    assert data["profile"] == "server"
    assert data["gpus"][0]["name"] == "NVIDIA L4"


def test_cli_exits_3_on_environment_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    hung = fake_probes(smi_error=subprocess.TimeoutExpired(["nvidia-smi"], 10))
    monkeypatch.setattr(tapesift.cli, "Probes", lambda: hung)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == ExitCode.ENVIRONMENT
    assert "PROBLEM" in result.stdout


def test_cli_on_this_machine_runs() -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code in (ExitCode.OK, ExitCode.ENVIRONMENT)
    assert json.loads(result.stdout)["profile"] in {p.value for p in Profile}


# ---- vision extra ---------------------------------------------------------


def test_vision_extra_reported() -> None:
    packages = {"av": "19.0.1", "transformers": "5.20.2", "torch": "2.14.1"}
    report = diagnose(fake_probes(packages=packages), Path("/data"), "0.1.0")
    assert report.vision == "transformers 5.20.2, torch 2.14.1"
    assert not any("tapesift[vision]" in n for n in report.notes)


def test_vision_extra_missing_is_a_note() -> None:
    report = diagnose(fake_probes(packages={"av": "19.0.1"}), Path("/data"), "0.1.0")
    assert report.vision is None
    assert 'vision extra not installed: index skips captions; install "tapesift[vision]"' in (
        report.notes
    )
    assert "vision       not installed (index skips captions)" in render(report)
