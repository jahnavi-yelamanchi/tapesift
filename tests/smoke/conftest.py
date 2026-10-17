import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES: Path = Path(__file__).parents[1] / "fixtures"


@pytest.fixture(scope="session")
def manifest() -> Any:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
