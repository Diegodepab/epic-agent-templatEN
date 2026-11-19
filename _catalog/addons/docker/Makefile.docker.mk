.PHONY: up up-deps up-prod down logs

up: ## Start containerized development stack (profile: dev)
	docker compose --profile dev up -d --build

up-deps: ## Start auxiliary infrastructure services only (profile: deps)
	docker compose --profile deps up -d

up-prod: ## Start production-like container stack (profile: prod)
	docker compose --profile prod up -d --build

down: ## Stop all Docker Compose profile services
	docker compose --profile dev --profile deps --profile prod --profile gpu down

logs: ## Follow container logs
	docker compose logs -f --tail=100
