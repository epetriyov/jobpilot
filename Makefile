# JobPilot — команды разработчика (AGENT_GUIDE.md §8)

COMPOSE ?= docker compose
UV ?= uv

.PHONY: up down test test-unit lint eval migrate backup restore smoke

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

test:
	$(UV) run pytest -q

test-unit:
	$(UV) run pytest -q -m "not integration"

lint:
	$(UV) run ruff check app tests eval
	$(UV) run ruff format --check app tests eval
	$(UV) run mypy
	$(UV) run lint-imports

# make eval CONTEXT=smoke
eval:
	$(UV) run python -m eval.runners.run --context $(CONTEXT)

migrate:
	$(UV) run alembic upgrade head

backup:
	./deploy/backup.sh

# make restore FILE=backups/jobpilot_YYYY-MM-DD.sql.gz
restore:
	./deploy/backup.sh restore $(FILE)

# тестовый DRY_RUN-прогон пайплайна на фикстурах (quickstart §4)
smoke:
	$(UV) run python -m app.worker.smoke
