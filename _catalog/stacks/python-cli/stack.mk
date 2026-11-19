.PHONY: dev lint format test

RUN := $(shell if command -v uv >/dev/null 2>&1; then echo "uv run"; else echo "python3 -m"; fi)

dev: ## Run CLI entrypoint in local environment
	$(RUN) {{PACKAGE_NAME}} --help

lint: ## Run Ruff and Mypy static checks
	$(RUN) ruff check src tests
	@if command -v mypy >/dev/null 2>&1 || [ -d .venv ]; then $(RUN) mypy src; fi

format: ## Format code and apply safe Ruff fixes
	$(RUN) ruff format src tests
	$(RUN) ruff check --fix src tests

test: ## Run Pytest suite
	$(RUN) pytest -q
