.PHONY: help install lint format typecheck test ci hooks

.DEFAULT_GOAL := help

install lint format format-check typecheck test ci:
	@uv run poe $@

hooks:
	chmod +x scripts/install-hooks scripts/pre-commit scripts/pre-push
	./scripts/install-hooks

help:
	@echo "django-easypay"
	@echo ""
	@echo "  poe --help    모든 태스크"
	@echo "  poe ci        전체 CI"
