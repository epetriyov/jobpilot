# Tasks: Прод-закалка (Этап 7)

**Input**: [spec.md](spec.md), [plan.md](plan.md), PLAN.md §Этап 7

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Операционная обвязка (репо)

- [x] T701 [US1] systemd-юнит `deploy/jobpilot.service`: Type=oneshot +
  RemainAfterExit=yes; After=docker.service network-online.target,
  Requires=docker.service; WorkingDirectory=<путь репо на VPS>;
  ExecStart=`docker compose up -d`, ExecStop=`docker compose down`;
  WantedBy=multi-user.target. COMPOSE_FILE/`.env` — из репо, не дублируются.
- [x] T702 [P] [US3] Healthcheck для `bot` и `worker` в `docker-compose.yml`:
  `CMD-SHELL "python -c 'import app' || exit 1"`, interval 30s/timeout 5s/retries 3/
  start_period 20s. Без сети и БД — иначе ложный unhealthy. db/alloy/mcp не трогаем.
- [x] T703 [US2] README: секции прод-операций — прод-деплой (тег→CI→GHCR→pull,
  пиннинг `JOBPILOT_IMAGE`, запрет `git pull`+build на VPS), восстановление из
  бэкапа (stop worker/bot → restore → migrate → up), ротация секретов (.env vs
  GitHub Secrets), OAuth Gmail (oauth_gmail CLI → .env → рестарт worker),
  systemd/ребут. Обновить статус этапа 0 → этапы 0–6 в проде, этап 7.
- [x] T704 [P] Валидация: `docker compose config -q` без ошибок.

## Phase 2: Ручная приёмка владельца (owner-side, на VPS)

- [ ] T705 [US1] Установить systemd-юнит на VPS: поправить WorkingDirectory под
  реальный путь (VPS_APP_DIR) → `sudo cp deploy/jobpilot.service
  /etc/systemd/system/` → `systemctl daemon-reload` → `systemctl enable --now
  jobpilot` → `systemctl status jobpilot` = active (exited).
- [ ] T706 [US1] Ребут-тест: `sudo reboot` → после старта `docker compose ps` все
  сервисы running/healthy, бот отвечает владельцу.
- [ ] T707 [US2] Restore-drill: свежий `make backup` → на тестовой БД пройти
  порядок stop worker/bot → `make restore FILE=...` → `make migrate` → up →
  проверить целостность данных (напр. `/stats` в боте).
- [ ] T708 [US2] End-to-end деплой по тегу: убедиться, что `JOBPILOT_IMAGE` пинит
  конкретный тег; пуш `vX.Y.Z` → image.yml собрал → deploy.yml сделал
  pull + up `--no-build` + migrate; VPS образ не собирал.
