.PHONY: dev lint format test

dev: ## Start backend and frontend development processes via Compose dev profile
	docker compose --profile dev up --build

lint: ## Lint both backend and frontend modules
	@if [ -d backend ]; then (cd backend && uv run ruff check src tests); fi
	@if [ -f frontend/package.json ]; then (cd frontend && npm run lint); fi

format: ## Format backend and frontend code
	@if [ -d backend ]; then (cd backend && uv run ruff format src tests); fi
	@if [ -f frontend/package.json ]; then (cd frontend && npm run format); fi

test: ## Run backend and frontend automated tests
	@if [ -d backend ]; then (cd backend && uv run pytest -q); fi
	@if [ -f frontend/package.json ]; then (cd frontend && npm test); fi
