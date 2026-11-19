.PHONY: dev lint format test

RUN := $(shell if command -v uv >/dev/null 2>&1; then echo "uv run"; else echo "python3 -m"; fi)

dev: ## Start local backend development server
	$(RUN) python -m {{PACKAGE_NAME}}.main

lint: ## Run Ruff, Mypy, and backend quality gates
	$(RUN) ruff check src tests
	@if command -v mypy >/dev/null 2>&1 || [ -d .venv ]; then $(RUN) mypy src; fi

format: ## Format backend Python files
	$(RUN) ruff format src tests
	$(RUN) ruff check --fix src tests

test: ## Run Pytest suite
	$(RUN) pytest -q
