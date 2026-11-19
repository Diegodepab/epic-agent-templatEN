.PHONY: dev lint format test

RUN := $(shell if command -v uv >/dev/null 2>&1; then echo "uv run"; else echo "python3 -m"; fi)

dev: ## Run local ML pipeline check on resolved compute device
	$(RUN) python -m {{PACKAGE_NAME}}.device

lint: ## Run Ruff and Mypy static checks
	$(RUN) ruff check src tests
	@if command -v mypy >/dev/null 2>&1 || [ -d .venv ]; then $(RUN) mypy src; fi

format: ## Format ML/GPU Python code
	$(RUN) ruff format src tests
	$(RUN) ruff check --fix src tests

test: ## Run CPU-safe unit tests
	$(RUN) pytest -q
