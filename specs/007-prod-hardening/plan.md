# Plan: Прод-закалка (Этап 7)

**Spec**: [spec.md](spec.md) · **Tasks**: [tasks.md](tasks.md)

## Подход

Этап не вводит нового кода приложения — только операционную обвязку поверх уже
работающего прода. Артефакты:

1. **Авто-подъём после ребута** — systemd-юнит `deploy/jobpilot.service`
   (Type=oneshot + RemainAfterExit, `docker compose up -d`). Переменные и
   COMPOSE_FILE не дублируются — читаются из `.env` репо на VPS. Дополняет уже
   существующий `restart: unless-stopped` у сервисов.
2. **Healthcheck bot/worker** — лёгкий liveness `python -c 'import app'`, без сети
   и БД (иначе моргание db/OTLP → ложный unhealthy). Без новых зависимостей.
3. **README — runbook прод-операций** — секции: прод-деплой (тег → CI → GHCR →
   pull, пиннинг `JOBPILOT_IMAGE`, запрет `git pull`+build на VPS), восстановление
   из бэкапа (порядок stop→restore→migrate→up), ротация секретов (.env vs GitHub
   Secrets), OAuth Gmail (oauth_gmail CLI → .env → рестарт worker), systemd/ребут.

## Валидация

- `docker compose config -q` — compose остаётся валидным.
- Ручная приёмка владельцем: ребут-тест, restore-drill, деплой по README.

## Вне scope

Изменения логики, миграций, CI-workflows; новые сервисы мониторинга (алерты уже
настроены на этапе 0/2).
