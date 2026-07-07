# Tasks: Фундамент и DevEx (Этап 0)

**Input**: Design documents from `/specs/000-foundation-devex/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: обязательны (constitution II, test-first): каждая задача реализации начинается с падающего теста по кейсу TEST_CASES.md. Ссылки на кейсы — в скобках `[…]`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Каркас репозитория по plan.md: `pyproject.toml` (uv, Python 3.12, зависимости, ruff/mypy/pytest/import-linter конфиг), пакеты `app/{domain/{shared,sourcing},ports,application,adapters/{llm,persistence,telegram},bot,worker,obs}`, `tests/{unit,contract,integration,golden}`, `.gitignore`
- [x] T002 [P] Контракт слоёв import-linter в pyproject: domain ← ports ← application ← (adapters|bot|worker); нарушение валит `make lint` (constitution I)
- [x] T003 [P] `Makefile`: up/down/test/eval/lint/migrate/backup/restore/smoke (AGENT_GUIDE.md §8)

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T004 [F-U1] Красный тест `tests/unit/test_config.py`: отсутствие обязательной переменной → понятная ошибка с именем → реализация `app/config.py` (pydantic-settings, contracts/env.md)
- [x] T005 [P] `app/obs/logging.py`: structlog JSON + процессор-санитайзер секретов; красный тест [X-U1] `tests/unit/test_log_sanitizer.py` (значения секретов из тестового env не встречаются в логах)
- [ ] T006 [P] `app/obs/tracing.py` + `app/obs/metrics.py`: инициализация OTel (OTLP → alloy), единая точка метрик (`job_runs_total`, `vacancies_discovered_total`, `llm_tokens_total`, `llm_cost_usd_total`, `scraper_failures_total`, `digest_sent_total`); недоступность коллектора не роняет сервис (edge case спеки)

## Phase 3: User Story 1 — Безопасный фундамент (P1) 🎯 MVP

**Goal**: домен shared+sourcing, хранение, бот only-owner, DRY_RUN-смоук, compose.

**Independent Test**: quickstart.md §1–3, §6.

- [x] T007 [P] [US1] Красные тесты домена shared `tests/unit/domain/test_shared.py`: SourceRef (site требует site_name, as_key), Salary — все поля опциональны → реализация `app/domain/shared/`
- [x] T008 [P] [US1] Красные тесты sourcing [S-U1] [S-U2] [S-U3] [S-U4] `tests/unit/domain/test_sourcing.py`: дедуп S1, кросс-дедуп S2 (30 дней), очистка HTML S3, изоляция падения источника S4 → реализация `app/domain/sourcing/` (Vacancy, normalize_company_title, content_hash, collect_from_sources, события)
- [x] T009 [US1] Порты `app/ports/`: VacancySourcePort, NotifierPort, репозитории (contracts/repositories.md) — Protocol-интерфейсы, зависят только от домена
- [x] T010 [US1] [F-I1] Красный integration-тест `tests/integration/test_migrations.py` (testcontainers, pgvector/pg16): `alembic upgrade head` создаёт seen_vacancy, labeled_vacancy, llm_call, job_run; повторный прогон идемпотентен → SQLAlchemy-модели `app/adapters/persistence/models.py` + миграция `0001_foundation` + репозитории
- [x] T011 [US1] [F-U2] Красный тест `tests/unit/test_owner_only.py`: чужой chat_id → молчаливый игнор + warning → `app/bot/` (aiogram, OwnerOnlyMiddleware, /start, /ping)
- [x] T012 [US1] [F-I2] Красный тест `tests/integration/test_dry_run.py`: DRY_RUN=true → publish-мок не вызван, дайджест помечен «ТЕСТ» → use case `app/application/smoke_pipeline.py` (сбор фикстур → дедуп → скоринг фейком → нотификация)
- [ ] T013 [US1] Dockerfile + docker-compose.yml (bot, worker, db=pgvector:pg16 без публикации порта наружу, alloy) + healthchecks; `make up` с нуля

## Phase 4: User Story 2 — Наблюдаемость и алерты (P2)

**Goal**: JobRun-журнал, телеметрия в Grafana Cloud, дашборд, алерты в Telegram.

**Independent Test**: quickstart.md §4–5.

- [x] T014 [US2] [F-I3] Красный тест `tests/integration/test_job_run.py`: упавший job → job_run.status=error, error заполнен, trace_id сквозной в логах → `app/worker/job_runner.py` (root span + JobRun + structlog bind trace_id), точка входа `app/worker/__main__.py` (APScheduler, Europe/Moscow)
- [ ] T015 [P] [US2] `deploy/alloy/config.alloy`: OTLP-приём (4317) → batch → Grafana Cloud (env-подстановки GRAFANA_CLOUD_*); host-метрики; graceful работа без кредов (локальный режим)
- [ ] T016 [P] [US2] `deploy/grafana/dashboard.json`: панели job'ов (успех/ошибки), вакансии по источникам, LLM-токены/стоимость
- [ ] T017 [P] [US2] `deploy/grafana/alerts/` + `provision.sh`: contact point Telegram (владелец) и правила — job failed; дайджест не отправлен к 10:15 МСК; scraper_failures (research.md §3)

## Phase 5: User Story 3 — Рельсы качества: CI/ревью/деплой (P2)

**Goal**: GitHub Actions без секретов на PR, агент-ревью, деплой по тегу.

**Independent Test**: quickstart.md §8.

- [ ] T018 [P] [US3] `.github/workflows/ci.yml`: jobs lint (ruff+mypy+import-linter), test (unit+contract), integration (Postgres service), recorded-eval — всё без внешних ключей [FR-015]
- [ ] T019 [P] [US3] `.github/workflows/claude-code-review.yml`: anthropics/claude-code-action@v1, промпт «соответствие спеке этапа и constitution»
- [ ] T020 [P] [US3] `.github/workflows/deploy.yml`: по тегу `v*`, SSH на VPS (секреты VPS_*), checkout тега → compose build/up → migrate
- [ ] T021 [P] [US3] `.env.example` по contracts/env.md (без значений) + README-раздел «Секреты и креды»

## Phase 6: User Story 4 — Учёт LLM и восстановимость (P3)

**Goal**: LlmPort + адаптеры с учётом llm_call, eval-каркас, бэкапы.

**Independent Test**: quickstart.md §1 (eval), §7 (бэкап); `pytest tests/contract`.

- [x] T022 [US4] [F-U3] [R-U1] Красные тесты `tests/unit/test_llm_fake.py`: вызов фейка → запись llm_call с токенами и cost_usd; невалидный ответ → 1 retry → None (graceful skip) → `app/ports/llm.py` (contracts/llm-port.md) + `app/adapters/llm/fake.py`
- [x] T023 [US4] [R-C2] [R-C3] Красный contract-suite `tests/contract/test_llm_port_suite.py`, параметризованный fake + instructor_openrouter (respx, записанные ответы `tests/golden/openrouter/`): валидная схема, ровно 1 retry, llm_call у каждого адаптера, cost_usd из usage (фолбэк — прайс конфига), модель из конфига без изменения кода → `app/adapters/llm/instructor_openrouter.py`
- [ ] T024 [P] [US4] Каркас eval: `eval/datasets/` (формат Приложения TEST_CASES.md, демо-датасет `smoke/v1.jsonl`), `eval/runners/` (базовый раннер с порогами-assertions, отчёт в `eval/reports/<name>_<date>.md`), `make eval CONTEXT=smoke`
- [ ] T025 [P] [US4] [X-I2] `deploy/backup.sh` (pg_dump, gzip, ротация 14 дней) + красный integration-тест `tests/integration/test_backup_restore.py`: dump → restore на чистую БД → счётчики строк совпадают

## Phase 7: Polish & Cross-Cutting

- [x] T026 [X-I1] E2E smoke-тест `tests/integration/test_e2e_smoke.py`: полный DRY_RUN-пайплайн на фикстурах → digest сформирован, job_run success, каждый шаг — OTel child span (in-memory exporter)
- [ ] T027 Финальный прогон: `make lint` + `make test` + `make eval CONTEXT=smoke` зелёные; quickstart.md актуален; отчёт пользователю (DoD AGENT_GUIDE.md §7)

## Dependencies & Execution Order

- Phase 1 → Phase 2 → истории; US1 (T007–T013) — MVP, блокирует смысловую проверку остальных.
- T010 зависит от T007–T009; T012 — от T008, T009, T022 (фейк LLM используется смоуком; допустимо реализовать T022 раньше T012).
- US2 (T014) зависит от T010 (таблица job_run); T015–T017 независимы [P].
- US3 независим от US2/US4, кроме T018, которому нужны существующие тесты (после T004+).
- US4: T022 → T023; T024, T025 параллельны.

## Соответствие кейсам TEST_CASES.md (раздел 0 + сквозные)

| Кейс | Задача |
|---|---|
| [F-U1] | T004 |
| [F-U2] | T011 |
| [F-U3] | T022 |
| [F-I1] | T010 |
| [F-I2] | T012 |
| [F-I3] | T014 |
| [S-U1..U4] | T008 |
| [R-U1] | T022 |
| [R-C2], [R-C3] | T023 |
| [X-U1] | T005 |
| [X-I1] | T026 |
| [X-I2] | T025 |
