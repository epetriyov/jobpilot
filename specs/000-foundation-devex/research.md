# Research: Фундамент и DevEx (Этап 0)

Все ключевые технологии зафиксированы пользователем в PLAN.md §2–3; research закрывает открытые вопросы реализации.

## 1. LLM-доступ: instructor поверх OpenRouter

- **Decision**: `instructor.from_openai(AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY), mode=instructor.Mode.JSON)`; response_model — pydantic; `max_retries=1`, после — graceful skip (инвариант R2). Имя модели — параметр вызова, берётся из конфига per-purpose (`LLM_MODEL_SCORING`, ...).
- **Rationale**: один ключ на все модели; OpenAI-совместимый API — instructor работает без спец-адаптера; свап модели = смена строки конфига (требование PLAN.md §2). Mode.JSON надёжнее tool-calling для моделей Gemini через OpenRouter.
- **cost_usd**: OpenRouter возвращает `usage` c `cost` при `extra_body={"usage": {"include": true}}` — берём фактический; фолбэк — `PRICE_PER_MTOK_IN/OUT` из конфига.
- **Alternatives considered**: прямые SDK провайдеров (нужен ключ на каждого, свап = код — отвергнуто PLAN.md); litellm (лишний слой поверх той же идеи, instructor уже выбран).

## 2. Телеметрия: OTel SDK → Grafana Alloy → Grafana Cloud

- **Decision**: сервисы шлют OTLP/gRPC на `alloy:4317` (внутри compose-сети). Alloy: `otelcol.receiver.otlp` → `otelcol.processor.batch` → `otelcol.exporter.otlphttp` в Grafana Cloud OTLP-endpoint c basic-auth (`GRAFANA_CLOUD_INSTANCE_ID` / `GRAFANA_CLOUD_API_TOKEN`). Метрики хоста/докера — `prometheus.exporter.unix` + `prometheus.exporter.cadvisor` в Alloy (VPS; на macOS cadvisor-часть неактивна).
- **Rationale**: единая точка выхода наружу, сервисы не знают кредов Grafana Cloud (безопасность: ключи только у Alloy); буферизация при недоступности облака.
- **Логи**: structlog JSON в stdout; в OTel-пайплайн логи отправляются через OTLP log exporter (bridge stdlib logging → OTel), Alloy пересылает в Loki-endpoint Grafana Cloud. Fallback: `docker logs` всегда доступен.
- **Alternatives considered**: прямой экспорт из сервисов в Grafana Cloud (креды в каждом сервисе, нет буфера — отвергнуто); Grafana Agent (deprecated в пользу Alloy).

## 3. Алерты: Grafana Alerting → Telegram

- **Decision**: алерт-правила и contact point (Telegram: `TELEGRAM_API_TOKEN` + `OWNER_CHAT_ID`) описываются файлами provisioning (`deploy/grafana/alerts/*.yaml`, формат Grafana Alerting v1) и заводятся в Grafana Cloud через API-скрипт `deploy/grafana/provision.sh` (curl к `/api/v1/provisioning/*`). Правила: (1) `job_runs_total{status="error"} > 0` за 15м — job failed; (2) отсутствие инкремента `digest_sent_total` к 10:15 МСК (07:15 UTC) — «дайджест не отправлен»; (3) `scraper_failures_total` рост за 30м.
- **Rationale**: free-тариф Grafana Cloud не даёт файлового provisioning — только API/UI; файлы в репо дают воспроизводимость, скрипт — автоматизацию.
- **Alternatives considered**: алерты в Alloy/самодельный алертер в worker (дублирует готовый Grafana Alerting, больше кода — отвергнуто); Terraform grafana provider (тяжеловесно для одного пользователя).

## 4. Integration-тесты БД

- **Decision**: testcontainers-python с образом `pgvector/pgvector:pg16`; фикстура сессионного уровня, `alembic upgrade head` прогоняется в тесте [F-I1]. Локально без Docker и в CI-джобе unit+contract интеграционные тесты скипаются маркером `integration` (в CI — отдельная джоба с services: postgres).
- **Rationale**: реальный Postgres (pgvector-типы), идемпотентность миграций проверяется честно.
- **Alternatives considered**: SQLite (нет pgvector/enum — ложная уверенность); общий dev-Postgres (флейки, состояние).

## 5. Recorded-eval в CI без ключей

- **Decision**: contract-suite LlmPort параметризуется адаптерами: `fake` (детерминированные ответы) и `instructor_openrouter` поверх respx-моков с записанными JSON-ответами OpenRouter (`tests/golden/openrouter/*.json`). `make eval` на этапе 0 гоняет демо-контекст `smoke` на фейковом провайдере и пишет отчёт в `eval/reports/`.
- **Rationale**: [R-C2] требует одинаковый suite для всех адаптеров; CI без секретов — требование PLAN.md §2 и FR-015.

## 6. Деплой по тегу

- **Decision**: `deploy.yml` на `push: tags: v*`: ssh (appleboy/ssh-action) на VPS → `git fetch && git checkout <tag> && docker compose build && docker compose up -d && alembic upgrade head`. Секреты: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` из GitHub Secrets.
- **Alternatives considered**: push-образов в GHCR + pull на VPS (лучше при нескольких хостах; для одного VPS build-on-host проще и дешевле — принято как этап-0 решение, GHCR — возможное улучшение этапа 7).

## 7. Агент-ревью PR

- **Decision**: `anthropics/claude-code-action@v1` в отдельном workflow `claude-code-review.yml` (trigger: pull_request), промпт нацелен на проверку соответствия спеке этапа и constitution; требует `ANTHROPIC_API_KEY` в GitHub Secrets (запрашивается у пользователя).

## 8. Санитайзер секретов в логах

- **Decision**: structlog-процессор, собирающий значения секретов из Settings (все поля с пометкой secret) и заменяющий вхождения на `***` в любом поле события. Тест [X-U1] прогоняет логирование с тестовыми секретами в env.
- **Rationale**: константная защита от случайного попадания токена в лог — дешевле, чем полагаться на дисциплину.

## 9. Нумерация фичи

- **Decision**: каталог `specs/000-foundation-devex` (номер = номеру этапа PLAN.md, `--number 0` в create-new-feature.sh); следующие этапы — 001…007.
