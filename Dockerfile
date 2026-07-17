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
# профиль кандидата для промпта скоринга и каркас eval-датасетов (этап 1)
COPY resumes ./resumes
COPY eval ./eval
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Chromium для web-скрейпера HH (пересмотр 2026-07-15) — только когда нужен реальный
# web-источник: тяжёлый (~400 МБ). По умолчанию OFF, чтобы dev/fake-сборки были лёгкими.
#   docker build --build-arg INSTALL_BROWSERS=true .
ARG INSTALL_BROWSERS=false
RUN if [ "$INSTALL_BROWSERS" = "true" ]; then \
      playwright install --with-deps chromium; \
    fi

# По умолчанию — бот; worker переопределяет command в compose
CMD ["python", "-m", "app.bot"]
