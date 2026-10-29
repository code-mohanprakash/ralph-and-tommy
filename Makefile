.PHONY: install lint types test check

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest

check: lint types test
