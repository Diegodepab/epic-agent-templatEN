.PHONY: dev lint format test clean

PKG_MGR := $(shell if [ -f pnpm-lock.yaml ]; then echo pnpm; else echo npm; fi)

dev: ## Start local frontend dev server
	$(PKG_MGR) run dev

lint: ## Run frontend lint and typecheck scripts
	$(PKG_MGR) run lint

format: ## Format frontend source files
	$(PKG_MGR) run format

test: ## Run frontend test suite and production build check
	$(PKG_MGR) test && $(PKG_MGR) run build
