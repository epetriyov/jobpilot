# JobPilot

Telegram-агент поиска работы. Методология: Spec-Driven (GitHub spec-kit) + DDD + TDD.
Источники истины: [PLAN.md](PLAN.md) → [docs/DOMAIN.md](docs/DOMAIN.md) →
[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md) → [docs/TEST_CASES.md](docs/TEST_CASES.md) →
[.specify/memory/constitution.md](.specify/memory/constitution.md) (высший приоритет).

Текущий статус: **этап 0 — фундамент и DevEx** (см. [specs/000-foundation-devex/](specs/000-foundation-devex/)).

## Быстрый старт (локально)

```bash
uv sync --all-extras
# .env ведётся владельцем локально (в git не попадает); список переменных —
# specs/000-foundation-devex/contracts/env.md
make lint                 # ruff + mypy + import-linter
make test                 # unit + contract (+ integration при наличии Docker)
make eval CONTEXT=smoke   # eval-прогон → отчёт в eval/reports/
make up && make migrate   # docker compose (bot, worker, db, alloy) + миграции
make smoke                # тестовый DRY_RUN-прогон пайплайна
```

Полная инструкция ручной проверки этапа: [specs/000-foundation-devex/quickstart.md](specs/000-foundation-devex/quickstart.md).

## Команды

| Команда | Действие |
|---|---|
| `make up` / `make down` | docker compose поднять/остановить |
| `make test` | unit + contract + integration |
| `make lint` | ruff + mypy + import-linter (границы слоёв) |
| `make eval CONTEXT=<name>` | eval-прогон контекста |
| `make migrate` | alembic upgrade head |
| `make backup` / `make restore FILE=...` | бэкап/восстановление БД |
| `make smoke` | DRY_RUN-прогон пайплайна на фикстурах |

## Секреты и креды

Все секреты — только в окружении, никогда в коде/логах/промптах (constitution IV).
Единственный источник — локальный `.env` владельца (в git не попадает); полный
перечень переменных — [contracts/env.md](specs/000-foundation-devex/contracts/env.md):

**В `.env` (локально и на VPS):**
- `TELEGRAM_API_TOKEN` — токен бота (@BotFather)
- `OWNER_CHAT_ID` — ваш chat_id (@userinfobot)
- `OPENROUTER_API_KEY` — ключ OpenRouter (все LLM)
- `POSTGRES_*` — доступ к БД
- `GRAFANA_CLOUD_OTLP_ENDPOINT`, `GRAFANA_CLOUD_INSTANCE_ID`, `GRAFANA_CLOUD_API_TOKEN` —
  креды бесплатного аккаунта Grafana Cloud (заводит владелец; до этого телеметрия локальна)

**В GitHub Secrets (не в `.env`):**
- `ANTHROPIC_API_KEY` — авторевью PR (claude-code-action)
- `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_DIR` — деплой по тегу (deploy.yml)
- `GRAFANA_URL`, `GRAFANA_SA_TOKEN`, `METRICS_DS_UID` — для `deploy/grafana/provision.sh`

## Архитектура

Гексагональная, границы слоёв обязательны (import-linter в CI):
`domain` (чистый, без I/O) ← `ports` ← `application` ← (`adapters` | `bot` | `worker`).
Подробнее — [docs/DOMAIN.md](docs/DOMAIN.md) и [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md).
