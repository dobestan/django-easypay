.PHONY: install lint format typecheck test ci hooks help

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make lint       - Run ruff check"
	@echo "  make format     - Run ruff format"
	@echo "  make typecheck  - Run mypy"
	@echo "  make test       - Run pytest"
	@echo "  make ci         - Run all CI checks (lint, format, typecheck, test)"
	@echo "  make hooks      - Install git hooks"

install:
	uv sync --group dev

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy easypay/

test:
	uv run pytest tests/ -v

ci: lint format-check typecheck test
	@echo "✅ All CI checks passed!"

hooks:
	chmod +x scripts/install-hooks scripts/pre-commit scripts/pre-push
	./scripts/install-hooks
