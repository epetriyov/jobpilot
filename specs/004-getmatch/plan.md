# Implementation Plan: Работа с GetMatch (Этап 4)

**Branch**: `004-getmatch` | **Date**: 2026-08-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-getmatch/spec.md`

## Summary

Новый источник вакансий GetMatch за существующим `VacancySourcePort` — **без изменения домена Sourcing** (DOMAIN.md §5: «новый источник = новый адаптер + golden + canary»). Доступ — **публичный JSON `GET /api/offers`** через **httpx** (research §1); Playwright/Chromium НЕ используются, источник исполняется на текущем 1 GB-железе (research §4, `docs/INFRA.md`). Парсинг — чистая функция `parse_getmatch_offers(payload) -> list[VacancyDTO]` над JSON, покрытая golden-diff тестом. Изоляция падений (S4) и деградация непарсенного в raw-секцию (S5, [S-C6]); блок/анти-бот → `SourceFetchFailed` + эскалация, без обхода (constitution IV). Активация — флагом источника, по умолчанию выключен до owner-canary (VI). Eval `getmatch_parse` accuracy ≥95% ([S-E1]). Новых таблиц нет — работает минимальный слой `seen_vacancy` (этап 1).

## Technical Context

**Language/Version**: Python 3.12 (стек этапов 0–3, без изменений)

**Dependencies**: `httpx` (уже в проекте), `beautifulsoup4` (уже — очистка HTML `offer_description`, S3). **Новых зависимостей нет. Никакого Playwright/Telethon.**

**Storage**: миграций **нет** — GetMatch пишет в существующий `seen_vacancy` (снапшот + скоринг этапа 1) как обычный источник.

**Constraints**: 1 rps, честный User-Agent, таймауты/ретрай+backoff (PLAN §7.3); ноль обхода анти-бота/капчи (S5); источник исполним на 1 vCPU / ~1 GB без Chromium; CI без сети (golden + fake).

**Scale/Scope**: ~779 активных offers на дату (research §3); пагинация `offset/limit`; в дайджест — после дедупа и скоринга, ≤50/день суммарно по всем источникам (R4).

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Слои | Парсер и маппинг — чистая функция в `adapters/getmatch/parser.py` (без I/O); адаптер `GetMatchSource` реализует порт; домен Sourcing не трогается; композиция источника — в сборке пайплайна | PASS |
| II. Test-first | [S-C5] (golden JSON → маппинг), [S-C6] (неизвестный формат → raw), [S-U1] (дедуп), [S-U4] (изоляция) — красные до кода; golden-diff как регресс-сигнал | PASS |
| III. LLM | Скоринг — существующий путь RELEVANCE (без нового промпта); тексты вакансий GetMatch — недоверенные данные, обёрнуты как данные (R5) | PASS |
| IV. Безопасность | Анти-бот/блок → `SourceFetchFailed` + эскалация, **без обхода** (S5); robots `Disallow:/api/` → включение только по owner-approval (research §2); секретов у источника нет (публичный фид) | PASS |
| V. Наблюдаемость | Сбор через `run_job` → JobRun + OTel span; метрика `scraper_failures{source="getmatch"}`; счётчик собранных offers | PASS |
| VI. Человек в контуре | Источник выключен по умолчанию; 2 дня canary отдельной секцией → `/approve_scraper getmatch`; ToS-решение за владельцем | PASS |

## Project Structure

```text
app/
├── adapters/getmatch/
│   ├── __init__.py
│   ├── source.py          # NEW: GetMatchSource(VacancySourcePort): httpx, пагинация offset/limit,
│   │                       #      1 rps, honest UA, timeouts/retry; блок/не-JSON → SourceFetchFailed (S4/S5)
│   └── parser.py          # NEW: parse_getmatch_offers(payload: dict) -> list[VacancyDTO]  (ЧИСТАЯ функция)
├── domain/sourcing/       # БЕЗ ИЗМЕНЕНИЙ (Source уже включает getmatch, §1 DOMAIN)
├── ports/                 # БЕЗ ИЗМЕНЕНИЙ (VacancySourcePort)
└── worker/ | application/ # +регистрация источника getmatch по флагу в сборке RunDailyDigest

tests/
├── golden/getmatch/
│   ├── README.md
│   ├── offers.json                 # обезличенный реальный ответ /api/offers (≥20 offers)
│   └── offers_unknown_format.json  # offer без position/url → [S-C6]
├── contract/test_getmatch_source.py # [S-C5], [S-C6], [S-U1] на golden + мок httpx
└── unit/... (маппинг Salary/HTML — если выносится)

eval/datasets/getmatch_parse/v1.jsonl  # [S-E1] accuracy ≥0.95
eval/runners/getmatch_parse.py          # + диспетчер в run.py
```

**Structure Decision**: зеркало API-адаптеров проекта (httpx + чистый парсер + golden-diff), как JSON-скрейперы этапа 5, а не как Playwright-хвост HH. Fake-режим — стаб-источник, отдающий golden (паттерн `HH_MODE=fake`).

## Сверка с DOMAIN.md / TEST_CASES.md / INFRA.md

- **DOMAIN.md §3.1**: `VacancySourcePort.fetch() -> list[VacancyDTO]`, инварианты S1 (дедуп по SourceRef), S3 (HTML→text), S4 (изоляция), S5 (анти-бот → SourceFetchFailed, не обход). `Source.GETMATCH` = значение `getmatch`, уже в едином языке §1 → **домен и §5-порядок расширения соблюдены, файл DOMAIN.md менять не нужно**.
- **TEST_CASES.md §1**: [S-C5], [S-C6], [S-E1] описаны как «корпус реальных сообщений бота GetMatch». Источник сменился на JSON API → формулировки этих кейсов нужно уточнить (`сообщения бота` → `JSON-ответ /api/offers`) **в том же PR** (constitution: уточнение домена → обновление TEST_CASES). Задача T408. Семантика кейсов (accuracy ≥95%, неизвестный формат → raw) сохраняется.
- **INFRA.md**: httpx-путь без Chromium → источник **не гейтится апгрейдом железа** (в отличие от этапа 5). Явно зафиксировано в spec SC-004 и tasks.
- **AGENT_GUIDE §5 (расширение домена)**: «Новый источник = новый адаптер `VacancySourcePort` + golden-тесты + canary. Домен Sourcing не меняется» — выполняется буквально.

## Risks & Mitigations

| Риск | Митигация |
|---|---|
| robots `Disallow:/api/` (ToS) | Источник off по умолчанию; включение только owner-approval после canary (research §2); обход не проектируем |
| GetMatch закроет `/api/offers` за логин / включит капчу | `SourceFetchFailed` + эскалация (S5); fallback — авторизованный хвост (research §5) отдельной спекой или скип; домен не страдает |
| Изменение структуры JSON | golden-diff тест падает с сигналом «парсер сломан» ([S-C0b]-аналог) |
| Публичный фид не персонализирован под резюме | Приемлемо: релевантность считает наш RELEVANCE; персональный фид — отложенный хвост |
| `company.name=null` (инкогнито) | Плейсхолдер/None, offer не отбрасывается (edge case spec) |
