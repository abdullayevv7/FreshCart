.PHONY: help build up down restart logs migrate makemigrations superuser shell test lint seed clean

COMPOSE = docker compose
BACKEND = $(COMPOSE) exec backend
MANAGE = $(BACKEND) python manage.py

help: ## Show this help message
	@echo "FreshCart - Grocery Delivery Platform"
	@echo "======================================"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Docker ───────────────────────────────────────────

build: ## Build all Docker containers
	$(COMPOSE) build

up: ## Start all services in detached mode
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) restart

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

logs-backend: ## Tail backend logs
	$(COMPOSE) logs -f backend

logs-celery: ## Tail Celery worker logs
	$(COMPOSE) logs -f celery_worker

logs-frontend: ## Tail frontend logs
	$(COMPOSE) logs -f frontend

ps: ## Show running containers
	$(COMPOSE) ps

# ── Django Management ────────────────────────────────

migrate: ## Run database migrations
	$(MANAGE) migrate

makemigrations: ## Create new migrations
	$(MANAGE) makemigrations

superuser: ## Create a superuser account
	$(MANAGE) createsuperuser

shell: ## Open Django shell (shell_plus if available)
	$(MANAGE) shell_plus 2>/dev/null || $(MANAGE) shell

dbshell: ## Open database shell
	$(MANAGE) dbshell

collectstatic: ## Collect static files
	$(MANAGE) collectstatic --noinput

showmigrations: ## Show migration status
	$(MANAGE) showmigrations

# ── Testing & Quality ───────────────────────────────

test: ## Run backend tests
	$(BACKEND) pytest -v --tb=short

test-cov: ## Run tests with coverage report
	$(BACKEND) pytest --cov=apps --cov-report=html --cov-report=term-missing

lint: ## Run linting (flake8 + black check)
	$(BACKEND) flake8 .
	$(BACKEND) black --check .

format: ## Auto-format code with black and isort
	$(BACKEND) black .
	$(BACKEND) isort .

# ── Frontend ─────────────────────────────────────────

frontend-install: ## Install frontend dependencies
	$(COMPOSE) exec frontend npm install

frontend-build: ## Build frontend for production
	$(COMPOSE) exec frontend npm run build

frontend-lint: ## Lint frontend code
	$(COMPOSE) exec frontend npm run lint

# ── Database ─────────────────────────────────────────

seed: ## Seed database with sample data
	$(MANAGE) seed_data

db-reset: ## Reset database (WARNING: destroys all data)
	$(COMPOSE) down -v
	$(COMPOSE) up -d db redis
	@echo "Waiting for database to be ready..."
	@sleep 5
	$(COMPOSE) up -d backend
	@sleep 3
	$(MANAGE) migrate
	@echo "Database has been reset."

db-backup: ## Create a database backup
	$(COMPOSE) exec db pg_dump -U $${POSTGRES_USER:-freshcart} $${POSTGRES_DB:-freshcart} > backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backup created."

db-restore: ## Restore database from backup (usage: make db-restore FILE=backup.sql)
	cat $(FILE) | $(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-freshcart} $${POSTGRES_DB:-freshcart}

# ── Celery ───────────────────────────────────────────

celery-restart: ## Restart Celery workers
	$(COMPOSE) restart celery_worker celery_beat

celery-purge: ## Purge all pending Celery tasks
	$(BACKEND) celery -A config purge -f

# ── Utilities ────────────────────────────────────────

clean: ## Remove all containers, volumes, and build cache
	$(COMPOSE) down -v --rmi local --remove-orphans
	docker system prune -f

redis-cli: ## Open Redis CLI
	$(COMPOSE) exec redis redis-cli

check: ## Run Django system checks
	$(MANAGE) check --deploy

flush-redis: ## Flush all Redis data
	$(COMPOSE) exec redis redis-cli FLUSHALL

generate-secret: ## Generate a new Django secret key
	@python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>/dev/null || \
		python -c "import secrets; print(secrets.token_urlsafe(50))"
