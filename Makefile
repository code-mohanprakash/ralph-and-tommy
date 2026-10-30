.PHONY: install hooks lint types test secrets check

install:
	uv sync

hooks:
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest

# The same key scan as the commit hook, over every tracked file.
# Hooks can be skipped with --no-verify; this can't, once CI runs it.
secrets:
	uv run pre-commit run no-api-keys --all-files

check: lint types test secrets
