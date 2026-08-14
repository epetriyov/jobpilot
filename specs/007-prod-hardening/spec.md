# Feature Specification: Прод-закалка (Этап 7)

**Feature Branch**: `007-prod-hardening`

**Created**: 2026-08-12

**Status**: Phase 1 (repo, T701–T704) shipped; Phase 2 owner-side acceptance (T705–T708) pending

**Input**: PLAN.md §Этап 7 — «systemd, healthchecks, README (деплой, восстановление,
ротация секретов, OAuth-флоу), deploy.yml проверен end-to-end, smoke на VPS».

## Цель

Довести уже работающий прод (этапы 0–6 на VPS VDSina, тег v0.3.0 на момент
написания спеки; актуальный прод — v0.8.2) до состояния
«закалён»: после перезагрузки VPS стек поднимается сам; операции деплоя,
восстановления, ротации секретов и перевыпуска OAuth-токена задокументированы так,
что владелец выполняет их по README без реверс-инжиниринга.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Перезагрузка VPS не требует ручного вмешательства (P1)

Владелец (или хостер) перезагружает VPS. Весь стек (db, bot, worker, alloy)
поднимается автоматически, без ручного `docker compose up`.

**Independent Test**: `sudo reboot` на VPS → после старта `docker compose ps`
показывает все сервисы running (healthy), бот отвечает владельцу.

**Acceptance Scenarios**:
1. **Given** установлен и включён systemd-юнит `jobpilot.service`, **When** VPS
   перезагружается, **Then** после старта docker все сервисы стека running,
   COMPOSE_FILE/`.env` подхвачены, порты наружу закрыты (UFW: только 22).
2. **Given** временный сбой одного контейнера, **When** он падает, **Then**
   `restart: unless-stopped` поднимает его без участия владельца.

### User Story 2 — Деплой с нуля и восстановление из бэкапа по README (P1)

Владелец разворачивает прод на чистой машине и восстанавливает БД из дампа,
следуя только README, без обращения к исходникам workflow.

**Independent Test**: пройти README-разделы «Прод-деплой» и «Восстановление из
бэкапа» на чистом окружении → рабочий стек с данными из дампа.

**Acceptance Scenarios**:
1. **Given** пустой VPS с `.env` и `JOBPILOT_IMAGE`-пином, **When** пуш git-тега
   `vX.Y.Z`, **Then** CI собирает образ в GHCR, deploy.yml делает pull + up
   `--no-build` + `alembic upgrade head`; VPS образ не собирает.
2. **Given** свежий дамп `backups/*.sql.gz`, **When** владелец выполняет restore по
   README (stop worker/bot → restore → migrate → up), **Then** данные восстановлены,
   схема на HEAD, сервисы работают.

### User Story 3 — Здоровье сервисов видно и секреты ротируются (P2)

bot и worker имеют healthcheck (docker показывает healthy/unhealthy). Ротация
секретов и перевыпуск OAuth Gmail выполняются по README без даунтайма БД.

**Independent Test**: `docker compose ps` показывает healthy для bot/worker;
смена `OPENROUTER_API_KEY` в `.env` + `up -d worker` подхватывает новое значение.

## Acceptance (DoD этапа, PLAN.md)

- ✅ Перезагрузка VPS → всё поднимается само (systemd + restart-policy).
- 🖐 Деплой по README с нуля + restore из бэкапа (ручная приёмка владельцем).
- healthcheck bot/worker присутствует и не даёт ложных unhealthy (без сети/БД).
- README содержит: прод-деплой, восстановление, ротацию секретов, OAuth-флоу, systemd.

## Ограничения

- Логика приложения, миграции и CI-workflows не меняются.
- Секреты — только через окружение (constitution IV).
- VPS никогда не собирает образ (OOM на 1 GB без swap).
