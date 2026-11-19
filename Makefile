.PHONY: help setup dev lint format test verify clean
.DEFAULT_GOAL := help

help: ## Show available project commands
	@echo "Available commands:"
	@grep -h -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install project dependencies and git hooks
	@if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	@if [ -d .git ] && command -v pre-commit >/dev/null 2>&1; then pre-commit install --hook-type pre-commit --hook-type commit-msg; fi

dev: ## Start local development mode (configured per stack)
	@echo "No 'dev' command configured yet. Select a stack via init_project.py or project-bootstrap."

lint: ## Run static analysis and linting checks (configured per stack)
	@echo "No 'lint' command configured yet. Select a stack via init_project.py or project-bootstrap."

format: ## Format code and apply safe autofixes (configured per stack)
	@echo "No 'format' command configured yet. Select a stack via init_project.py or project-bootstrap."

test: ## Run automated test suite (configured per stack)
	@echo "No 'test' command configured yet. Select a stack via init_project.py or project-bootstrap."

verify: lint test ## Run full quality gate before committing or opening a PR

clean: ## Remove temporary build, cache, and coverage artifacts
	rm -rf dist build out coverage tmp

# Optional modular makefiles (e.g., .make/stack.mk, .make/docker.mk)
-include .make/*.mk
