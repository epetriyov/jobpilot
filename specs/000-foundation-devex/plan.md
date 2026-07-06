# Implementation Plan: Фундамент и DevEx (Этап 0)

**Branch**: `000-foundation-devex` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/000-foundation-devex/spec.md`

## Summary

Заложить фундамент JobPilot: воспроизводимое docker-окружение (bot, worker, db, alloy), чистый домен shared+sourcing по DOMAIN.md §3.1, минимальный слой хранения (§4: seen_vacancy, labeled_vacancy, llm_call, job_run) с Alembic-миграциями, `LlmPort` (instructor в openai-режиме поверх OpenRouter + фейковый провайдер), сквозную наблюдаемость (structlog JSON + OTel SDK → Grafana Alloy → Grafana Cloud, дашборд + алерты в Telegram), DRY_RUN-смоук пайплайна, backup.sh, каркас eval/ и рельсы качества на GitHub (CI, claude-code-action ревью, deploy по тегу). Всё — строго TDD по кейсам раздела 0 TEST_CASES.md.

## Technical Context

**Language/Version**: Python 3.12 (PLAN.md §3)

**Primary Dependencies**: aiogram 3, APScheduler, httpx, instructor + openai-SDK (base_url OpenRouter), SQLAlchemy 2 + Alembic, pydantic v2 + pydantic-settings, structlog, OpenTelemetry SDK (+OTLP exporters), Docker Compose, Grafana Alloy (контейнер)

**Storage**: PostgreSQL 16 + pgvector (образ `pgvector/pgvector:pg16`); время в БД — UTC

**Testing**: pytest (+pytest-asyncio), respx (HTTP-моки), testcontainers-python (integration, Postgres), фейковый LlmPort (contract), import-linter (слои), ruff, mypy

**Target Platform**: Ubuntu VPS (VDSina) под Docker Compose; локальная разработка — macOS

**Project Type**: backend-монорепо: один Python-пакет `app/` с гексагональными слоями + интерфейсные точки входа bot/worker

**Performance Goals**: не критичны на этапе 0; телеметрия не должна блокировать пайплайн (batched OTLP export)

**Constraints**: домен без I/O (import-linter); CI без внешних ключей (recorded-eval, фейковый LlmPort); секреты только env; Postgres наружу не публикуется; бот — long polling

**Scale/Scope**: один пользователь (OWNER_CHAT_ID); ~десятки вакансий/день; этап 0 — каркас без реальных источников

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Как соблюдается в этом плане | Статус |
|---|---|---|
| I. Домен чист, слои нерушимы | `app/domain/` — только stdlib+pydantic; направление domain ← ports ← application ← (adapters\|bot\|worker); контракт import-linter в `pyproject.toml`, гоняется в `make lint` и CI | PASS |
| II. Test-first, без исключений | Каждая задача tasks.md начинается с красного теста по кейсу TEST_CASES.md раздела 0 (+S-U*, R-U1, R-C2/C3, X-U1, X-I2); пирамида U→C→I; красные тесты в main запрещены CI | PASS |
| III. LLM — измеряемая зависимость | Все вызовы через `LlmPort`; instructor+pydantic-схема; модели/прайсы из конфига (`LLM_MODEL_*`); каждый вызов → `llm_call` (O1); каркас eval/ с append-only датасетами; Langfuse — с этапа 1 (профиль compose подготовлен), llm_call закрывает учёт на этапе 0 | PASS |
| IV. Безопасность по умолчанию | Секреты только env (`.env`, `.env.example` без значений); санитайзер structlog + тест [X-U1]; DRY_RUN уважается пайплайном; Postgres не публикуется; бот отвечает только владельцу | PASS |
| V. Наблюдаемость — не опция | JobRun + root span на каждый job; child spans на шаги; structlog с trace_id; метрики через `obs/metrics.py`; llm_call.cost_usd; дашборд и алерты — артефакты deploy/grafana/ | PASS |
| VI. Человек в контуре | Этап 0 не совершает внешних действий вообще (DRY_RUN по умолчанию); деплой — по явному тегу; ручная проверка пользователем закрывает этап | PASS |

Нарушений нет → Complexity Tracking не заполняется.

## Project Structure

### Documentation (this feature)

```text
specs/000-foundation-devex/
├── plan.md              # этот файл
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 — ручная проверка (DoD)
├── contracts/           # Phase 1 — контракты портов и env
│   ├── llm-port.md
│   ├── repositories.md
│   └── env.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
jobpilot/
├── .github/workflows/       # ci.yml, claude-code-review.yml, deploy.yml
├── .specify/                # spec-kit (memory/constitution.md — высший приоритет)
├── specs/000-foundation-devex/
├── app/
│   ├── config.py             # pydantic-settings; F-U1
│   ├── domain/
│   │   ├── shared/           # SourceRef, Salary, DomainEvent, PromptVersion, TraceId
│   │   └── sourcing/         # Vacancy, дедуп-сервис, события (S1–S4)
│   ├── ports/                # VacancySourcePort, LlmPort, NotifierPort, репозитории
│   ├── application/          # RunSmokePipeline (DRY_RUN-смоук этапа 0)
│   ├── adapters/
│   │   ├── llm/              # instructor_openrouter.py, fake.py, prompts/
│   │   ├── persistence/      # SQLAlchemy-модели, репозитории, alembic/
│   │   └── telegram/         # NotifierPort-адаптер (aiogram)
│   ├── bot/                  # точка входа бота; owner-only middleware
│   ├── worker/               # точка входа APScheduler; JobRun-раннер
│   └── obs/                  # structlog+санитайзер, OTel-инициализация, metrics.py
├── tests/
│   ├── unit/  contract/  integration/  golden/
├── eval/
│   ├── datasets/  runners/  reports/
├── deploy/
│   ├── alloy/config.alloy    # OTLP-приём → Grafana Cloud
│   ├── grafana/dashboard.json
│   ├── grafana/alerts/       # provisioning-файлы Grafana Alerting
│   └── backup.sh
├── docker-compose.yml        # bot, worker, db, alloy (+профили langfuse/mcp позже)
├── Dockerfile
├── Makefile                  # up/down/test/eval/lint/migrate/backup/restore
├── pyproject.toml            # deps, ruff, mypy, import-linter, pytest
└── .env.example
```

**Structure Decision**: единый пакет `app/` с гексагональными слоями строго по PLAN.md §4; `bot/` и `worker/` — тонкие точки входа поверх `application/`. Тесты по пирамиде AGENT_GUIDE.md §3. Инфраструктура — `deploy/` + корневые compose/Dockerfile/Makefile.

## Сверка с DOMAIN.md

- Термины кода дословно из §1: `Vacancy`, `SourceRef`, `Salary`, `Score`, `Label`, `JobRun`, `LlmCall`, `DRY_RUN`.
- Инварианты S1–S4 (§3.1) — доменные тесты [S-U1..U4]; R2/R5-механика LlmPort — [R-U1], [R-C2]; O1/O2 (§3.6) — [F-U3], [F-I3], [X-I1].
- Модель данных — §4 минимальный слой: seen_vacancy, labeled_vacancy (+embedding vector(768) — колонка есть, заполняется с этапа 6), llm_call, job_run. Таблицы inbox_message/linkedin_target из §4 создаются на этапах 2–3 своими миграциями (одна миграция = один этап).

## Сверка с AGENT_GUIDE.md

- §2: правила слоёв → контракт import-linter (провал = провал CI/lint).
- §3: пирамида тестов → unit (домен), contract (фейковый LlmPort, respx, записанные ответы OpenRouter), integration (testcontainers Postgres).
- §4: LlmPort/instructor/конфиг моделей/промпт-версии/anti-injection — контракт `contracts/llm-port.md`.
- §5: obs-обязанности → `obs/`, структура логов, запреты (тела писем, значения секретов).
- §8: команды Makefile — как в гайде.
