.PHONY: install fmt lint typecheck arch test verify contracts-schema run

SRC = src tests ../../packages/contracts/python ../../scripts

install:
	uv sync

fmt:
	uv run ruff format $(SRC)

lint:
	uv run ruff check $(SRC)

typecheck:
	uv run mypy src tests ../../packages/contracts/python ../../scripts

arch:
	uv run pytest tests/architecture -q

test:
	uv run pytest -q

contracts-schema:
	uv run python -m mochi_contracts.export_schema ../../packages/contracts/schema

verify:
	uv run ruff format --check $(SRC)
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) arch
	uv run pytest -q
	uv run python -m mochi_contracts.export_schema ../../packages/contracts/schema --check

run:
	uv run uvicorn mochi_backend.app:app_from_env --factory --reload --port 8000
