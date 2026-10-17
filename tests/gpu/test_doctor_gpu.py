"""Doctor on a real NVIDIA machine. Runs on Modal via scripts/cloud/modal_gpu.py."""

from pathlib import Path

import pytest

from tapesift.cli.doctor import Probes, Profile, diagnose

pytestmark = pytest.mark.gpu


def test_doctor_sees_the_gpu() -> None:
    report = diagnose(Probes(), Path.cwd(), "test")
    assert report.problems == []
    assert report.gpus, "nvidia-smi found no GPU"
    assert report.cuda is not None
    assert report.profile in (Profile.GPU, Profile.SERVER)
    assert all(g.vram_mib > 0 and g.driver for g in report.gpus)


def test_datacenter_gpus_have_nvdec() -> None:
    # Every GPU in SERVER_GPUS ships an NVDEC engine; a False here means the
    # decoder-utilization heuristic in parse_gpus is wrong for this driver.
    report = diagnose(Probes(), Path.cwd(), "test")
    if report.profile is Profile.SERVER:
        assert all(g.nvdec for g in report.gpus)
