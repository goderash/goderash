.PHONY: help setup dev stop clean test lint type format migrate seed build release

PY := python3
UV := uv
PNPM := pnpm

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup:  ## One-time setup (deps, DB, first migration)
	@echo "==> Installing Python workspace (uv)"
	$(UV) sync
	@echo "==> Installing Node workspace (pnpm)"
	$(PNPM) install
	@echo "==> Copy .env.example if .env not present"
	@test -f .env || cp .env.example .env
	@echo "==> Done. Run 'make dev' to start."

dev:  ## Start Postgres + Redis + control plane + dashboard
	docker compose -f infra/docker/docker-compose.yml up --build

dev-bg:  ## Start stack in background
	docker compose -f infra/docker/docker-compose.yml up -d --build

stop:  ## Stop all services
	docker compose -f infra/docker/docker-compose.yml down

clean:  ## Stop + remove volumes
	docker compose -f infra/docker/docker-compose.yml down -v

test:  ## Run tests (Python + TS)
	cd python/core && $(UV) run pytest --tb=short -q
	cd python/goderash_sdk && $(UV) run pytest --tb=short -q
	$(PNPM) -r test

lint:  ## Lint Python + TS
	cd python/core && $(UV) run ruff check src tests
	cd python/goderash_sdk && $(UV) run ruff check src tests
	$(PNPM) -r lint

type:  ## Type check Python + TS
	cd python/core && $(UV) run mypy src
	cd python/goderash_sdk && $(UV) run mypy src
	$(PNPM) -r typecheck

format:  ## Autoformat Python + TS
	cd python/core && $(UV) run black src tests && $(UV) run isort src tests
	cd python/goderash_sdk && $(UV) run black src tests && $(UV) run isort src tests
	$(PNPM) -r format

migrate:  ## Apply Alembic migrations
	cd python/core && $(UV) run alembic upgrade head

migrate-new:  ## Generate a new migration: make migrate-new m="describe change"
	cd python/core && $(UV) run alembic revision --autogenerate -m "$(m)"

seed:  ## Seed local DB with demo tenant + API key
	cd python/core && $(UV) run python -m goderash_core.scripts.seed

build:  ## Build production images
	docker compose -f infra/docker/docker-compose.yml build

release-py:  ## Release Python packages to PyPI (CI-only; uses OIDC)
	cd python/goderash_sdk && $(UV) build && $(UV) publish
	cd python/goderash_adapter_langgraph && $(UV) build && $(UV) publish

release-ts:  ## Release TS packages to npm
	$(PNPM) -r publish --access public
