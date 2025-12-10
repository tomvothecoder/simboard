# ============================================================
#  SimBoard Backend Makefile
#  Description: Common developer commands for local use
# ============================================================

# Variables
APP_NAME=app.main
HOST=127.0.0.1
PORT=8000

# Colors
GREEN=\033[0;32m
NC=\033[0m

# ============================================================
#  Setup & Environment
# ============================================================
.PHONY: install sync clean

install:
	@echo "$(GREEN)Creating environment...$(NC)"
	uv venv .venv
	$(MAKE) sync

sync:
	@echo "$(GREEN)Installing dependencies...$(NC)"
	uv sync --all-groups

clean:
	@echo "$(GREEN)Cleaning cache and build files...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf dist build .mypy_cache .ruff_cache

# ============================================================
#  Development Server
# ============================================================

.PHONY: run reload

run:
	@echo "$(GREEN)Starting FastAPI server over HTTPS...$(NC)"
	uv run uvicorn $(APP_NAME):app \
		--host $(HOST) \
		--port $(PORT) \
		--ssl-keyfile ../certs/key.pem \
		--ssl-certfile ../certs/cert.pem

reload:
	@echo "$(GREEN)Starting FastAPI server with auto-reload over HTTPS...$(NC)"
	uv run uvicorn $(APP_NAME):app \
		--reload \
		--host $(HOST) \
		--port $(PORT) \
		--ssl-keyfile ../certs/key.pem \
		--ssl-certfile ../certs/cert.pem

reload-debug:
	@echo "$(GREEN)Starting FastAPI server with auto-reload and debug logging over HTTPS...$(NC)"
	uv run uvicorn $(APP_NAME):app \
		--reload \
		--host $(HOST) \
		--port $(PORT) \
		--log-level debug \
		--ssl-keyfile ../certs/key.pem \
		--ssl-certfile ../certs/cert.pem

# ============================================================
#  Database Migrations (Alembic)
# ============================================================

.PHONY: migrate upgrade downgrade history current

migrate:
	@echo "$(GREEN)Generating new Alembic migration...$(NC)"
	uv run alembic revision --autogenerate -m "$(m)"

upgrade:
	@echo "$(GREEN)Upgrading database to latest migration...$(NC)"
	uv run alembic upgrade head

downgrade:
	@echo "$(GREEN)Downgrading database...$(NC)"
	uv run alembic downgrade $(rev)

history:
	@echo "$(GREEN)Listing migration history...$(NC)"
	uv run alembic history

current:
	@echo "$(GREEN)Current database version:$(NC)"
	uv run alembic current

# ============================================================
#  Code Quality
# ============================================================

.PHONY: lint format

lint:
	@echo "$(GREEN)Linting with Ruff...$(NC)"
	uv run ruff check .

format:
	@echo "$(GREEN)Auto-fixing issues with Ruff...$(NC)"
	uv run ruff check . --fix

test:
	@echo "$(GREEN)Running tests with pytest...$(NC)"
	uv run pytest tests

# ============================================================
#  Misc
# ============================================================

.PHONY: help

help:
	@echo "$(GREEN)Available commands:$(NC)"
	@echo "  make install           - Create virtual environment and install dependencies"
	@echo "  make sync              - Install dependencies (all groups)"
	@echo "  make clean             - Remove caches and build artifacts"
	@echo "  make run               - Start FastAPI server"
	@echo "  make reload            - Start FastAPI server with auto-reload"
	@echo "  make reload-debug      - Start FastAPI server with auto-reload and debug logging"
	@echo "  make migrate m='msg'   - Create Alembic migration with message"
	@echo "  make upgrade           - Apply all migrations"
	@echo "  make downgrade rev=    - Downgrade to specific revision"
	@echo "  make history           - Show migration history"
	@echo "  make current           - Show current DB revision"
	@echo "  make lint              - Run linter (Ruff)"
	@echo "  make format            - Auto-fix code issues with Ruff"
	@echo "  make test              - Run tests with pytest"
