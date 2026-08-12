# Tasks: Работа с GetMatch (Этап 4)

**Input**: Design documents from `/specs/004-getmatch/`

**Tests**: обязательны (constitution II): красный тест по кейсу TEST_CASES.md §1 — до кода.

**Железо**: все задачи исполняются на **текущем VPS (1 vCPU / ~1 GB, без Chromium)** — источник httpx-based, Playwright НЕ требуется. Гейта апгрейда железа у этапа 4 нет (в отличие от этапа 5).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Foundational

- [x] T401 Конфиг/env: флаг источника GetMatch в общий список (`SOURCES` включает `getmatch` **или** `GETMATCH_MODE=auto|fake|real`, дефолт — источник выключен), `GETMATCH_API_URL`, `GETMATCH_USER_AGENT`, `GETMATCH_REQUEST_PAUSE_SEC`, `GETMATCH_PAGE_LIMIT` (contracts/env.md). Секретов нет (публичный фид). ([F-U1])
- [x] T402 [P] Golden: `tests/golden/getmatch/offers.json` (обезличенный ответ `/api/offers`: открытая вилка, `salary_hidden`, `company.name=null` инкогнито, `is_active=false`) + `offers_unknown_format.json` (offer без `position`/`url`) + `README.md`. Тесты, ссылающиеся на них, — красные. ([S-C5],[S-C6])
- [x] T403 Проверить/добавить `Source.GETMATCH = "getmatch"` в enum источников домена (использование заявленного значения DOMAIN §1 — не изменение домена); уже присутствует → no-op с тестом.

## Phase 2: US1 — вакансии GetMatch в дайджесте (P1) 🎯 MVP

- [x] T404 [US1] [S-C5] Красный contract-тест на `offers.json` → **чистая функция** `parse_getmatch_offers(payload) -> list[VacancyDTO]` (`adapters/getmatch/parser.py`): маппинг (data-model), дедуп по `id`, `salary_hidden`→`Salary(None,None,None)`, открытая/частичная вилка, HTML `offer_description` → `description_text` очищен (S3), `is_active=false` пропущен, `company.name=null` → плейсхолдер `GetMatch (скрыто)` (домен требует `company: str`). Golden-diff падает при смене структуры ([S-C0b]-аналог).
- [x] T405 [US1] [S-U1] Тест дедупа: повтор `id` в батче (парсер) и между страницами (адаптер) → дубликата нет; межпрогонный `SourceRef`/first_seen_at — общий пайплайн `seen_vacancy` (S1), не адаптер.
- [x] T406 [US1] Красный тест (мок httpx) → адаптер `GetMatchSource(VacancySourcePort)` (`adapters/getmatch/source.py`): `fetch()` — GET `/api/offers`, пагинация `offset += limit` до `meta.total`, пауза ≥`GETMATCH_REQUEST_PAUSE_SEC` (1 rps), honest UA, таймаут+ретрай с backoff; собранные offers → `parse_getmatch_offers`. `GETMATCH_MODE=fake` → стаб (прод-парсер), сети нет.

## Phase 3: US2 — изоляция и деградация в raw (P1)

- [x] T407 [US2] [S-C6] Тест: offer неизвестного формата (`offers_unknown_format.json`) → VacancyDTO не создаётся (парсер отдаёт []); raw-секция «непарсенное» + warning — общий путь дайджеста; пайплайн жив.
- [x] T408 [US2] [S-U4] Тест изоляции: GetMatch отдаёт 5xx / не-JSON / анти-бот-страницу → `GetMatchFetchError` (коллектор `RunDailyDigest._collect` → `scraper_failures{source="getmatch"}` + `job_run.status=partial`); анти-бот → эскалация владельцу, **без обхода** (S5, constitution IV); остальные источники собраны.

## Phase 4: Композиция и наблюдаемость

- [x] T409 [US1] Регистрация источника getmatch по флагу в сборке пайплайна (`build_getmatch_sources` + `Services._getmatch_sources`, влит в `run_digest`): выключен → не собирается; включён fake → стаб, real → httpx; общий ingest/скоринг; падение изолируется коллектором (S4), эскалация анти-бота через notifier владельцу.

## Phase 5: Eval и синхронизация кейсов

- [x] T410 [S-E1] Датасет `eval/datasets/getmatch_parse/v1.jsonl` (обезличенные offers → эталон title/company/url, ≥20) + раннер `eval/runners/getmatch_parse.py` + диспетчер в `run.py`; `make eval CONTEXT=getmatch_parse` → accuracy ≥0.95 (assertion). Отчёт в `eval/reports/`.
- [ ] T411 Синхронизация docs **в том же PR**: TEST_CASES.md §1 — уточнить формулировки [S-C5]/[S-C6]/[S-E1] (`сообщения бота GetMatch` → `JSON-ответ /api/offers`); PLAN §6 «Этап 4» — пометка о смене userbot→публичный JSON API (или сноска-пересмотр, как у HH 2026-07-17). Домен DOMAIN.md §3.1 не меняется.
- [ ] T412 Гейты зелёные: ruff / mypy / import-linter / pytest (unit+contract) + CI-eval в fake-режиме = PASS; отчёт по DoD (PLAN §7.6: сделано / acceptance / eval / что нужно для ручной проверки).

## Phase 6: Owner-приёмка

- [ ] T413 🖐 Владелец: 2 дня canary — GetMatch отдельной секцией дайджеста; сверка качества (title/company/url/вилка на реальных карточках) + **решение по robots/ToS** (research §2); при согласии — `/approve_scraper getmatch` → включение источника, при отказе — источник остаётся off (этап помечен отложенным с обоснованием).

## Dependencies

T401–T403 → T404 → T405 → T406 → (T407, T408) → T409 → T410 → T411 → T412 → T413.
T402 [P] независим от T401. T410 после T404 (парсер) и, для real-прогона, после доступности реального ответа (обезличенный golden достаточен для CI).

## Соответствие кейсам TEST_CASES.md (§1)

| Кейс | Задача |
|---|---|
| [S-C5] | T402, T404 |
| [S-C6] | T402, T407 |
| [S-U1] | T405 |
| [S-U4] | T408 |
| [S-E1] | T410 |
| [S-C0b]-аналог (golden-diff) | T404 |
| [F-U1] (конфиг) | T401 |
