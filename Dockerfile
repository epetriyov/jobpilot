# JobPilot — единый образ для bot и worker (разные команды запуска в compose).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# uv для быстрой установки зависимостей
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Слой зависимостей — кешируется отдельно от кода
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

# Код
COPY app ./app
COPY alembic.ini ./
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# По умолчанию — бот; worker переопределяет command в compose
CMD ["python", "-m", "app.bot"]
