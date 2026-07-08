# Quickstart: проверка этапа 0 руками

Пошаговая валидация acceptance-критериев этапа 0 (PLAN.md §6) и DoD (AGENT_GUIDE.md §7).

## Предусловия

- Docker + Docker Compose, `uv` (или Python 3.12), `make`.
- Заполненный локальный `.env` (перечень переменных — `contracts/env.md`): минимум `TELEGRAM_API_TOKEN`, `OWNER_CHAT_ID`, `OPENROUTER_API_KEY`; для облачной телеметрии — `GRAFANA_CLOUD_*` и `GCLOUD_HOSTED_METRICS_*`.

## 1. Локальные проверки без Docker

```bash
uv sync --all-extras     # окружение
make lint                # ruff + mypy + import-linter — зелёный
make test                # unit + contract (+integration при наличии Docker) — зелёный
make eval CONTEXT=smoke  # отчёт появляется в eval/reports/
```

## 2. Compose с нуля

```bash
make up                  # bot, worker, db, alloy
make migrate             # alembic upgrade head
docker compose ps        # все сервисы healthy/running
```

## 3. Бот отвечает только владельцу

- Написать боту `/start` со своего аккаунта (OWNER_CHAT_ID) → ответ приходит.
- Написать с любого другого аккаунта → тишина; в логах бота warning `foreign_chat_ignored`.

## 4. Телеметрия в Grafana Cloud

```bash
make smoke               # тестовый DRY_RUN-прогон пайплайна на фикстурах
```

- В Grafana Cloud (Explore → Traces/Tempo) виден трейс `smoke_pipeline` с child-спанами шагов.
- В Explore → Metrics (Mimir) есть `job_runs_total`, `vacancies_discovered_total`, `llm_tokens_total`, `llm_cost_usd_total`.
- В Explore → Logs (Loki) — structlog-события прогона с `trace_id`.

## 5. Алерты в Telegram

```bash
deploy/grafana/provision.sh   # заводит contact point + правила в Grafana Cloud
```

- В Grafana → Alerting → Contact points → Telegram-канал владельца → **Test** → сообщение приходит в Telegram.

## 6. DRY_RUN

- `DRY_RUN=true` (дефолт): `make smoke` → дайджест-заглушка помечена «ТЕСТ», publish-мок не вызван (лог `dry_run=true`).

## 7. Бэкап/восстановление

```bash
make backup                        # deploy/backup.sh → backups/jobpilot_YYYY-MM-DD.sql.gz
make restore FILE=backups/<файл>   # восстановление на чистую БД
```

## 8. CI и агент-ревью (после пуша на GitHub)

- Открыть тестовый PR → джобы lint / tests / recorded-eval зелёные; claude-code-action оставляет ревью-комментарий.
- Запушить тег `v0.0.1` → deploy.yml стартует (реальный деплой — при заведённых VPS-секретах).

## Ожидаемый итог

Все 8 пунктов проходят → acceptance этапа 0 выполнен; этап закрывается ручным подтверждением пользователя.
