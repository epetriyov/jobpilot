# JobPilot

Telegram-агент поиска работы. Методология: Spec-Driven (GitHub spec-kit) + DDD + TDD.
Источники истины: [PLAN.md](PLAN.md) → [docs/DOMAIN.md](docs/DOMAIN.md) →
[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md) → [docs/TEST_CASES.md](docs/TEST_CASES.md) →
[.specify/memory/constitution.md](.specify/memory/constitution.md) (высший приоритет).

Текущий статус: **этапы 0–6 в проде** (HH, письма, LinkedIn, GetMatch, скрейперы, CRM+MCP);
идёт **этап 7 — прод-закалка** (см. [specs/007-prod-hardening/](specs/007-prod-hardening/)).
Прод развёрнут на VPS VDSina, деплой по git-тегу (текущий — `v0.3.0`).

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

## Локальная разработка при работающем VPS

Обе среды живут одновременно; разведены конфигурацией (`.env` у каждой свой):

| | Локально (dev) | VPS (prod) |
|---|---|---|
| `TELEGRAM_API_TOKEN` | **тестовый бот** (второй, из @BotFather) | боевой бот |
| `DRY_RUN` | `true` всегда | `false` после включения боевого режима |
| `DEPLOY_ENV` | не задаётся (дефолт `dev`) | `prod` |

- Один и тот же токен бота в двух местах нельзя: Telegram отдаёт long polling
  только одному процессу (409 Conflict). Тестовый бот решает это навсегда.
- Телеметрия обеих сред идёт в общий Grafana Cloud; серии различаются лейблом
  `deployment_environment` (dev/prod). Алерты фильтруют только `prod` —
  локальные прогоны их не трогают. На дашборде можно смотреть обе среды.
- Внешние записи (publish HH) локально всегда отключены DRY_RUN.
- БД у сред раздельные (свои docker volume) — конфликтов нет.

Цикл проверки изменения: `make lint && make test` → `make up` → команды тестовому
боту в Telegram → `make down`. VPS всё это время работает как ни в чём не бывало.

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
- `CLAUDE_CODE_OAUTH_TOKEN` — авторевью PR (claude-code-action; из `claude setup-token`, подписка Max)
- `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_DIR` — деплой по тегу (deploy.yml)
- `GRAFANA_URL`, `GRAFANA_SA_TOKEN`, `METRICS_DS_UID` — для `deploy/grafana/provision.sh`

## Прод-операции (VPS)

На VPS в `.env`: `COMPOSE_FILE=docker-compose.yml:deploy/docker-compose.vps.yml`,
`JOBPILOT_IMAGE=ghcr.io/epetriyov/jobpilot:vX.Y.Z`, `DEPLOY_ENV=prod`, `DRY_RUN=false`.

### Прод-деплой (только по тегу)

Деплой запускается **исключительно git-тегом** — не `git pull` на VPS.

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

1. `.github/workflows/image.yml` собирает образ в CI и пушит в `ghcr.io/epetriyov/jobpilot:vX.Y.Z`.
2. `.github/workflows/deploy.yml` по SSH на VPS: `docker compose pull` → `docker compose up -d --no-build` → `alembic upgrade head`.

**VPS никогда не собирает образ** (`--no-build`): сборка на боксе 1 GB без swap
даёт OOM/kswapd0. **Обязательно пиньте конкретный тег** в `JOBPILOT_IMAGE` — иначе
разовый `docker compose run` подхватит устаревший fallback `jobpilot:local`.
Запрещено чинить прод через `git pull` + `docker compose up --build`.

### Восстановление из бэкапа

Бэкапы: `deploy/backup.sh` (cron ежедневно, ротация 14 дней, дампы в `backups/`).
Порядок restore (останавливаем писателей, чтобы не гонять запись во время загрузки):

```bash
docker compose stop worker bot
make restore FILE=backups/jobpilot_YYYY-MM-DD_HHMMSS.sql.gz
make migrate                 # alembic upgrade head — довести схему до HEAD
docker compose up -d worker bot
```

### Ротация секретов

Секреты живут в двух местах (см. раздел «Секреты и креды»):
- **`.env` на VPS** — рантайм-секреты (токены, ключи, POSTGRES_*). Ротация: правим
  значение в `/opt/jobpilot/.env` → рестарт затронутых сервисов:
  `docker compose up -d <service>` (например `worker` при смене `OPENROUTER_API_KEY`).
- **GitHub Secrets** — CI/деплой (`VPS_*`, `CLAUDE_CODE_OAUTH_TOKEN`, `GRAFANA_*`).
  Ротация — через Settings → Secrets, деплой не требуется.

Секреты — только в окружении, никогда в файлах/коде/логах (constitution IV).

### OAuth Gmail — перевыпуск токена

Gmail (основной источник HH — email) ходит по OAuth refresh-token. Consent-экран
Google переведён «In production» (иначе токен протухает за 7 дней). Перевыпуск:

```bash
uv run python -m app.cli.oauth_gmail        # локально: получить новый refresh-token
```

Перенести новый refresh-token в прод `/opt/jobpilot/.env` → `docker compose up -d worker`.

### systemd / перезагрузка VPS

Авто-подъём стека после ребута — [deploy/jobpilot.service](deploy/jobpilot.service)
(Type=oneshot, `docker compose up -d`; читает `.env`/COMPOSE_FILE репо). Установка:

```bash
sudo cp deploy/jobpilot.service /etc/systemd/system/jobpilot.service
sudo systemctl daemon-reload && sudo systemctl enable --now jobpilot
```

После этого перезагрузка VPS поднимает весь стек сама (сервисы также имеют
`restart: unless-stopped`).

## Архитектура

Гексагональная, границы слоёв обязательны (import-linter в CI):
`domain` (чистый, без I/O) ← `ports` ← `application` ← (`adapters` | `bot` | `worker`).
Подробнее — [docs/DOMAIN.md](docs/DOMAIN.md) и [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md).
