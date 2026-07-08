# Quickstart: проверка этапа 0 руками (локально + VPS с нуля)

Пошаговая валидация acceptance-критериев этапа 0 (PLAN.md §6) и DoD (AGENT_GUIDE.md §7).
Рассчитана на исходное состояние: **Docker нигде не установлен**; локально macOS + проект,
на VPS — чистая Ubuntu. Переменные окружения — локальный `.env` (перечень: `contracts/env.md`).

---

## Часть A. Локально БЕЗ Docker (можно прямо сейчас)

```bash
cd ~/Documents/projects/jobpilot
uv sync --all-extras          # окружение Python 3.12
make lint                     # ruff + mypy + import-linter → всё зелёное
make test-unit                # unit + contract (integration скипаются без Docker)
make eval CONTEXT=smoke       # → PASS, отчёт в eval/reports/smoke_<дата>.md
make smoke                    # DRY_RUN-прогон: в stdout дайджест с пометкой «ТЕСТ»
```

Ожидаемо в `make smoke`: строки structlog-JSON, дайджест «🧪 ТЕСТ (DRY_RUN)» с 2 фикстурными
вакансиями и предупреждения `Failed to export traces to alloy:4317` — это **норма без Docker**
(коллектора нет; недоступность телеметрии не роняет пайплайн — так и задумано).

---

## Часть B. Локально С Docker (integration-тесты + compose + телеметрия)

### B1. Установить Docker на macOS

Вариант 1 — Docker Desktop (проще всего):
```bash
brew install --cask docker
open -a Docker            # дождаться «Docker Desktop is running» в меню-баре
docker info               # проверка: без ошибок
```
Вариант 2 — colima (легковеснее, без GUI): `brew install colima docker docker-compose && colima start`.

### B2. Полный тестовый прогон (включая integration)

```bash
make test      # unit + contract + integration (testcontainers сам поднимет pgvector/pg16)
```
Проверяются: [F-I1] миграции идемпотентны, [F-I2] DRY_RUN, [F-I3] job_run при падении,
[X-I2] backup/restore, [X-I1] e2e-спаны. Первый запуск скачивает образ (~1–2 мин).

### B3. Compose с нуля + миграции

```bash
make up                # соберёт образ и поднимет bot, worker, db, alloy
docker compose ps      # db — healthy; bot/worker/alloy — running (Up)
make migrate           # alembic upgrade head (локально, DSN из .env указывает на localhost…
                       # …но порт db наружу НЕ публикуется — поэтому надёжнее через контейнер:)
docker compose run --rm worker alembic upgrade head
docker compose logs alloy --tail 20   # без ошибок конфига; экспорт в Grafana Cloud активен
```

### B4. Бот отвечает только владельцу ([F-U2])

1. В Telegram найдите своего бота, отправьте `/start` со своего аккаунта → ответ «JobPilot на связи…», `/ping` → «pong 🟢».
2. Отправьте боту сообщение с любого другого аккаунта → тишина; в логах:
   `docker compose logs bot | grep foreign_chat_ignored` → warning с chat_id.

⚠️ Не держите бот запущенным одновременно локально и на VPS: два long-polling на один
токен дают ошибку 409 Conflict от Telegram.

### B5. Телеметрия в Grafana Cloud

```bash
docker compose run --rm worker python -m app.worker.smoke   # прогон внутри сети compose
```
Затем в Grafana Cloud (ваш стек → Explore):
- **Tempo (Traces)**: сервис `jobpilot-worker`/`jobpilot-smoke` → трейс со спанами `smoke.collect → smoke.dedup → smoke.publish → smoke.notify`.
- **Mimir (Metrics)**: `digest_sent_total`, `vacancies_discovered_total`; хост-метрики `node_cpu_seconds_total` и др. (из `prometheus.exporter.unix` Alloy).
- **Loki (Logs)**: structlog-события `smoke_done`, `publish_skipped` с `trace_id`.

### B6. Дашборд

Grafana → Dashboards → New → **Import** → вставить содержимое `deploy/grafana/dashboard.json`
→ выбрать datasource метрик (grafanacloud-…-prom). Панели: job-прогоны, вакансии по
источникам, LLM-токены/стоимость, сбои скрейперов.

### B7. Алерты → Telegram

Нужны: `GRAFANA_URL` (https://<стек>.grafana.net), `GRAFANA_SA_TOKEN`
(Administration → Service accounts → токен с ролью Editor), `METRICS_DS_UID`
(Connections → Data sources → prom-датасорс → uid из URL).

```bash
export GRAFANA_URL=... GRAFANA_SA_TOKEN=... METRICS_DS_UID=...
export TELEGRAM_API_TOKEN=$(grep -m1 '^TELEGRAM_API_TOKEN=' .env | cut -d= -f2-)
export OWNER_CHAT_ID=$(grep -m1 '^OWNER_CHAT_ID=' .env | cut -d= -f2-)
uv run --with pyyaml -- bash deploy/grafana/provision.sh
```
Проверка: Grafana → Alerting → Contact points → `owner-telegram` → **Test** → сообщение
пришло в ваш Telegram. Правила: Alerting → Alert rules → папка JobPilot (3 правила).

### B8. Бэкап/восстановление ([X-I2])

```bash
make backup                                  # backups/jobpilot_<дата>.sql.gz
make restore FILE=backups/jobpilot_<дата>.sql.gz
```
Без локального pg_dump скрипт сам уходит в docker-режим (`docker compose exec db`).

---

## Часть C. GitHub (CI + агент-ревью) — по пути к VPS

Нужно один раз: репозиторий на GitHub (он же источник для VPS и deploy.yml).

```bash
brew install gh
gh auth login                                  # браузерная авторизация
cd ~/Documents/projects/jobpilot
gh repo create jobpilot --private --source . --push   # запушит main
git push -u origin 000-foundation-devex               # ветка этапа
gh secret set ANTHROPIC_API_KEY                        # для авторевью PR
# для деплоя по тегу (после настройки VPS, см. C ниже):
gh secret set VPS_HOST; gh secret set VPS_USER; gh secret set VPS_SSH_KEY; gh secret set VPS_APP_DIR
```

Проверка рельс: `gh pr create --base main --head 000-foundation-devex --title "Stage 0: foundation" --fill`
→ в PR: джобы lint / test / integration / recorded-eval зелёные, `claude-code-review` оставил комментарий.

⚠️ Перед первым push убедитесь: `git status` не показывает `.env` (он в .gitignore).

---

## Часть D. VPS (Ubuntu, с нуля)

### D1. Docker Engine + compose

```bash
ssh <user>@<vps>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && exit   # перелогиньтесь, чтобы группа применилась
ssh <user>@<vps>
docker info && docker compose version   # обе команды без ошибок
```

### D2. Файрвол (constitution IV: наружу только SSH)

```bash
sudo ufw allow OpenSSH && sudo ufw enable && sudo ufw status
# порты 4317/5432 и т.п. НЕ открываем — они живут внутри docker-сети
```

### D3. Код и .env

```bash
sudo mkdir -p /opt/jobpilot && sudo chown $USER /opt/jobpilot
git clone git@github.com:<вы>/jobpilot.git /opt/jobpilot   # или https + токен
cd /opt/jobpilot && git checkout 000-foundation-devex
```
`.env` в git нет — скопируйте локальный и ужесточите права:
```bash
# с локальной машины:
scp ~/Documents/projects/jobpilot/.env <user>@<vps>:/opt/jobpilot/.env
# на VPS:
chmod 600 /opt/jobpilot/.env
# включить VPS-оверлей с host-метриками (только на сервере, НЕ локально):
echo 'COMPOSE_FILE=docker-compose.yml:deploy/docker-compose.vps.yml' >> /opt/jobpilot/.env
```
Правка для VPS в `/opt/jobpilot/.env`: `POSTGRES_DSN` не нужен для контейнеров
(compose подставляет свой с host=db), но для скриптов оставьте как есть — backup.sh
на VPS работает через docker-режим и DSN не использует.

### D4. Запуск и миграции

```bash
cd /opt/jobpilot
docker compose up -d --build
docker compose ps                                    # db healthy, остальные Up
docker compose run --rm worker alembic upgrade head  # миграции
docker compose logs alloy --tail 20                  # экспорт в Grafana Cloud без ошибок
```

### D5. Проверки на VPS (те же, что B4–B5)

```bash
docker compose logs bot --tail 20                    # bot_starting, polling
docker compose run --rm worker python -m app.worker.smoke
docker compose logs bot | grep foreign_chat_ignored  # после сообщения с чужого аккаунта
```
- `/start` боту со своего аккаунта → ответ; с чужого → тишина + warning.
- Grafana Cloud: трейс smoke, метрики (включая `node_*` хоста VPS), логи — как в B5.
- Дашборд/алерты уже заведены в облаке (B6–B7) — общие для локали и VPS.

### D6. Ежедневный бэкап (cron)

```bash
crontab -e
# каждый день в 03:30 по времени сервера; ротация 14 дней встроена в скрипт
30 3 * * * cd /opt/jobpilot && ./deploy/backup.sh >> backups/backup.log 2>&1
```
Разовая проверка restore:
```bash
cd /opt/jobpilot && ./deploy/backup.sh
./deploy/backup.sh restore backups/jobpilot_<дата>.sql.gz
```

### D7. Деплой по тегу (проверка deploy.yml)

После `gh secret set VPS_*` (часть C):
```bash
# локально:
git tag v0.0.1 && git push origin v0.0.1
```
GitHub → Actions → Deploy: SSH на VPS, checkout тега, `compose build/up`, миграции.

---

## Итоговый чек-лист acceptance этапа 0

- [ ] A: lint / test-unit / eval / smoke — зелёные локально без Docker
- [ ] B2: `make test` полностью зелёный (integration на testcontainers)
- [ ] B3/D4: compose с нуля поднимается локально и на VPS; миграции идемпотентны
- [ ] B4/D5: бот отвечает владельцу, игнорирует чужих (warning в логах)
- [ ] B5/D5: трейс + метрики + логи smoke-прогона видны в Grafana Cloud
- [ ] B6: дашборд импортирован и показывает данные
- [ ] B7: тестовый алерт дошёл в Telegram
- [ ] B8/D6: бэкап и restore проходят; cron заведён
- [ ] C: CI на PR зелёный, комментарий агента-ревью есть
- [ ] D7: деплой по тегу отработал

Все пункты ✅ → этап 0 закрывается вашим подтверждением (DoD AGENT_GUIDE.md §7).
