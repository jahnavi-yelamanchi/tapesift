.PHONY: check fmt lint typecheck test smoke fixtures

# Everything CI runs. Must pass before any PR.
check: lint typecheck test

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest -q -m "not gpu"

smoke:
	uv run pytest tests/smoke -q

# Regenerates tests/fixtures/ (needs ffmpeg and espeak-ng; see ADR 0006, 0007).
fixtures:
	uv run python scripts/make_fixtures.py
