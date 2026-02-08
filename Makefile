# ─── AI Marketing Intelligence Platform ── Makefile ──────────────────────────
# Common development and operations commands.
# Usage: make <target>

.PHONY: help install migrate migrate-gen celery-worker celery-beat celery-export \
        celery-all keygen up up-prod down logs test lint

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────────────

install: ## Install Python dependencies
	pip install -e ".[dev]"

keygen: ## Generate a Fernet encryption key for TELEGRAM_ENCRYPTION_KEY
	@python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

secret: ## Generate a random SECRET_KEY value
	@python -c "import secrets; print(secrets.token_urlsafe(64))"

# ── Database ─────────────────────────────────────────────────────────────────

migrate: ## Run alembic migrations (upgrade head)
	cd backend && alembic upgrade head

migrate-gen: ## Auto-generate a new alembic migration (usage: make migrate-gen MSG="add foo table")
	cd backend && alembic revision --autogenerate -m "$(MSG)"

migrate-history: ## Show alembic migration history
	cd backend && alembic history --verbose

# ── Celery ───────────────────────────────────────────────────────────────────

celery-worker: ## Start the default Celery worker
	cd backend && celery -A app.workers.celery_app worker --loglevel=info -Q default,collection

celery-beat: ## Start the Celery beat scheduler
	cd backend && celery -A app.workers.celery_app beat --loglevel=info

celery-export: ## Start the export queue Celery worker
	cd backend && celery -A app.workers.celery_app worker -Q export --loglevel=info -c 2

celery-media: ## Start the media queue Celery worker
	cd backend && celery -A app.workers.celery_app worker -Q media --loglevel=info -c 1

celery-all: ## Start all Celery workers + beat (dev convenience, uses honcho/foreman style)
	@echo "Starting all Celery processes..."
	@echo "Use docker-compose for production. This target runs workers sequentially."
	cd backend && celery -A app.workers.celery_app worker --loglevel=info -Q default,collection &
	cd backend && celery -A app.workers.celery_app worker -Q export --loglevel=info -c 2 &
	cd backend && celery -A app.workers.celery_app worker -Q media --loglevel=info -c 1 &
	cd backend && celery -A app.workers.celery_app beat --loglevel=info

# ── Docker ───────────────────────────────────────────────────────────────────

up: ## Start development stack (docker-compose)
	docker compose up -d

up-prod: ## Start production stack
	docker compose -f docker-compose.prod.yml up -d

down: ## Stop all containers
	docker compose down

logs: ## Tail logs from all containers
	docker compose logs -f --tail=50

logs-export: ## Tail logs from export worker
	docker compose logs -f --tail=50 export-worker

# ── Development ──────────────────────────────────────────────────────────────

dev: ## Start FastAPI backend with hot-reload
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run pytest
	cd backend && pytest -v

lint: ## Run ruff linter
	ruff check backend/ bot/

lint-fix: ## Run ruff with auto-fix
	ruff check --fix backend/ bot/

format: ## Run ruff formatter
	ruff format backend/ bot/
