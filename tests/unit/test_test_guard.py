import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_guard() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "ci" / "test_guard.py"
    spec = importlib.util.spec_from_file_location("test_guard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_guard"] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def test_count_tests_finds_sync_and_async_tests() -> None:
    source = "def test_a():\n    pass\n\nasync def test_b():\n    pass\n\ndef helper():\n    pass\n"
    assert guard.count_tests(source) == 2


def test_uncited_skip_is_flagged() -> None:
    diff = "+++ b/tests/unit/test_x.py\n+@pytest.mark.skip(reason='flaky')\n"
    assert guard.uncited_skips(diff) == ["tests/unit/test_x.py: @pytest.mark.skip(reason='flaky')"]


def test_skip_citing_a_card_or_adr_passes() -> None:
    diff = (
        "+++ b/tests/gpu/test_nvdec.py\n"
        "+@pytest.mark.skipif(no_gpu, reason='card #41: no NVDEC on runners')\n"
        "+@pytest.mark.xfail(reason='ADR 0009 known drift')\n"
    )
    assert guard.uncited_skips(diff) == []


def test_removed_lines_are_ignored() -> None:
    diff = "+++ b/tests/unit/test_x.py\n-@pytest.mark.skip(reason='old')\n"
    assert guard.uncited_skips(diff) == []
