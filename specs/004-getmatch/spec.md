# Feature Specification: Работа с GetMatch (Этап 4)

**Feature Branch**: `004-getmatch`

**Created**: 2026-08-12

**Status**: Draft (пересмотр источника: userbot → публичный JSON API сайта)

**Input**: PLAN.md §6 «Этап 4. Работа с GetMatch»: чтение карточек вакансий GetMatch → общий пайплайн скоринга и дайджеста; непарсенное — raw-секцией; eval `getmatch_parse` accuracy ≥95%; деградация в raw без падения; 2 дня canary → подтверждение. **Пересмотр 2026-08-12**: исходный план (userbot Telethon, чтение бота GetMatch в Telegram) заблокирован — my.telegram.org стабильно отдаёт `ERROR` при создании api_id (та же стена, что у HH, см. `specs/001-hh-digest/research.md`, «Пересмотр 2026-07-17»). Владелец выбрал парсинг сайта getmatch.ru. Исследование доступа (research.md) показало: у GetMatch есть **публичный JSON-эндпоинт `GET /api/offers`** с полными полями вакансий, **без логина и без браузера** → источник «лёгкий» (httpx), Playwright/Chromium НЕ нужен, привязки к апгрейду железа нет.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Вакансии GetMatch в ежедневном дайджесте (Priority: P1)

Владелец получает в общем ежедневном дайджесте (10:00 МСК) релевантные вакансии из GetMatch наравне с вакансиями HH: каждая проходит дедуп, скоринг относительно резюме EM и попадает в дайджест с пометкой источника, если score ≥ порога. GetMatch — ещё один адаптер за `VacancySourcePort`; домен Sourcing, дедуп, скоринг и дайджест не меняются.

**Why this priority**: это продукт этапа — вакансии GetMatch в подборке; всё остальное (raw-деградация, canary) — обвязка вокруг сбора.

**Independent Test**: включить `SOURCES=...,getmatch` в DRY_RUN → в тестовом дайджесте появляются вакансии с source=`getmatch`, у каждой корректны title/company/url; вилка зарплаты, если открыта.

**Acceptance Scenarios**:

1. **Given** golden обезличенного JSON-ответа `GET /api/offers` (≥20 offers), **When** сбор источника getmatch, **Then** все VacancyDTO замаплены (title=`position`, company=`company.name`, url=`https://getmatch.ru{url}`), дедуп по `id` вакансии, `salary_hidden=true` → `Salary(None,None,None)`, `description_text` очищен от HTML (S3) ([S-C5]).
2. **Given** offer с открытой вилкой (`salary_hidden=false`, `salary_display_from=300000`, `salary_display_to=550000`, `salary_currency=RUB`), **Then** `Salary(from=300000, to=550000, currency="RUB")`; при только `from` без `to` → `Salary(from=X, to=None)` (S1, все поля Salary опциональны).
3. **Given** повторный сбор той же вакансии (тот же `SourceRef(getmatch, external_id=id)`), **Then** дубликат не создаётся, first_seen_at неизменён (S1, [S-U1]).
4. **Given** DRY_RUN=true, **Then** дайджест помечен «ТЕСТ», внешних записей нет (F-I2).

---

### User Story 2 - Изоляция падений и деградация в raw (Priority: P1)

Если GetMatch недоступен (сеть/5xx), отдал не-JSON, анти-бот-страницу или изменил структуру — сбор из остальных источников (HH-email и т.д.) не прерывается, а непарсенные offers уходят в raw-секцию дайджеста «непарсенное» с warning-логом, без падения пайплайна.

**Why this priority**: недоверенная внешняя среда (S5); без изоляции один источник роняет весь дайджест.

**Independent Test**: подсунуть адаптеру JSON нового/неизвестного формата → VacancyDTO не создаётся, raw-текст в секции «непарсенное», warning-лог; остальные источники собраны.

**Acceptance Scenarios**:

1. **Given** offer нового неизвестного формата (нет `position`/`url`), **Then** VacancyDTO не создаётся, raw-запись в секцию «непарсенное», warning-лог ([S-C6]).
2. **Given** GetMatch вернул 5xx / не-JSON / анти-бот-страницу, **Then** `SourceFetchFailed(source="getmatch", error)` + эскалация владельцу, **без обхода анти-бота/капчи** (S5, constitution IV); остальные источники собраны, `job_run.status=partial` (S4, [S-U4]).
3. **Given** GetMatch изменил структуру полей (модифицированный golden), **Then** golden-diff тест падает с сигналом «парсер GetMatch сломан» (как [S-C0b]/[S-C8]).

---

### Edge Cases

- `salary_hidden=true` (в выборке ~70% offers) → `Salary(None,None,None)`, вакансия всё равно скорится (вилка не обязательна, S1).
- `company.name = null` (инкогнито-публикация, `incognito_publication=true`) → company=`None` или плейсхолдер «GetMatch (скрыто)»; вакансия не отбрасывается.
- `is_active=false` в выдаче → offer пропускается (не показываем закрытые).
- Пагинация: `meta.total` (на момент исследования 779) > `limit` → адаптер листает `offset += limit` до `offset ≥ total`; при сбое на N-й странице — уже собранное отдаётся, ошибка страницы логируется (S4).
- `GETMATCH_MODE=fake` → детерминированный стаб-источник из golden (паттерн этапов 1–3), сеть не трогается; CI без сети.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Система MUST собирать вакансии GetMatch через адаптер `GetMatchSource(VacancySourcePort)` поверх **httpx** (публичный JSON `GET /api/offers`, пагинация `offset/limit`); домен Sourcing не меняется. Playwright/браузер НЕ используются — источник исполняется на текущем железе (1 vCPU / ~1 GB, без Chromium; см. `docs/INFRA.md`).
- **FR-002**: Парсер MUST быть чистой функцией `parse_getmatch_offers(payload: dict) -> list[VacancyDTO]` над JSON-ответом: маппинг полей (§data-model), дедуп по `id`, очистка HTML `offer_description` (S3), корректная обработка `salary_hidden`/частичной вилки ([S-C5]).
- **FR-003**: Непарсенный/неизвестного формата offer MUST NOT создавать VacancyDTO — уходит в raw-секцию «непарсенное» с warning-логом, пайплайн не падает ([S-C6], S5).
- **FR-004**: Недоступность/5xx/не-JSON/анти-бот-страница MUST давать `SourceFetchFailed(source="getmatch")` + эскалацию владельцу, **без обхода анти-бота/капчи** (S5, constitution IV); остальные источники собираются, `job_run.status=partial` (S4).
- **FR-005**: Адаптер MUST соблюдать вежливый доступ: 1 rps (пауза ≥1 c между страницами), честный User-Agent из конфига, таймауты/ретрай с backoff (PLAN §7.3); при `GETMATCH_MODE=fake` — детерминированный стаб из golden, сети нет.
- **FR-006**: Источник GetMatch MUST активироваться флагом в общем списке источников (`SOURCES`/`GETMATCH_MODE`); выключен по умолчанию до owner-приёмки (canary, VI).
- **FR-007**: MUST существовать eval-контекст `getmatch_parse` (JSONL: `payload offer → эталонные поля`): accuracy title/company/url ≥95% ([S-E1]).
- **FR-008**: Golden-diff тест MUST падать при изменении структуры JSON-ответа GetMatch (регресс-сигнал «парсер сломан», как [S-C0b]).

### Key Entities

- **Vacancy / VacancyDTO** (DOMAIN.md §3.1) — без изменений; новый `Source.GETMATCH` (значение `getmatch` уже в едином языке §1). `SourceRef(source=getmatch, site_name=None, external_id=str(offer.id))`.
- **Offer (внешний DTO GetMatch)** — сырой JSON-объект из `/api/offers` (не доменная сущность): `id, position, company.name, url, salary_display_from/to, salary_currency, salary_hidden, offer_description, skills_objects[], location_items[], published_at, is_active`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: В дайджесте (DRY_RUN, затем боевой) присутствуют вакансии с пометкой источника GetMatch, прошедшие скоринг; закрытые/непарсенные не ломают подборку (acceptance PLAN §6).
- **SC-002**: Кейсы [S-C5], [S-C6], [S-U1], [S-U4] зелёные; golden-diff ловит изменение структуры ([S-C0b]-аналог).
- **SC-003**: `make eval CONTEXT=getmatch_parse`: accuracy ≥95% ([S-E1]).
- **SC-004**: Источник исполняется на текущем VPS (1 vCPU / ~1 GB) без Chromium/Playwright — деплой не требует апгрейда железа (в отличие от этапа 5).
- **SC-005**: 🖐 2 дня canary отдельной секцией → владелец подтверждает качество и принимает ToS/robots-решение (см. Assumptions) → включение источника.

## Assumptions

- **Доступ — публичный JSON `GET /api/offers`** (подтверждено исследованием: HTTP 200, `{meta:{total,offset,limit}, offers:[...]}`, без логина, nginx+Next.js, признаков Cloudflare/капчи нет). Это предпочтительнее авторизованного парсинга сайта: `/vacancies` HTML рендерится на клиенте (в сыром HTML 0 карточек) и потребовал бы Playwright; JSON отдаёт всё готовым и лёгким httpx-запросом.
- **robots.txt содержит `Disallow: /api/`** — открытый вопрос ToS-соответствия (см. research §2). JobPilot ходит как персональный агент владельца (1 запрос/прогон, вежливый rate, читает офферы, адресованные кандидатам), а не как массовый краулер. Решение о допустимости — за владельцем (человек в контуре, VI): включение источника — только после явного `/approve_scraper getmatch` по итогам canary. Обхода анти-бота/блока не проектируем (S5): блок → эскалация.
- **Фильтры API не подтверждены**: пробные параметры (`salary_from`, `grades`, `specializations`) не влияли на `meta.total` — считаем, что серверных фильтров под наши имена нет; тянем полный активный фид и фильтруем/скорим на своей стороне (паттерн проекта: EM-фильтр на адаптере, скоринг LLM). Пагинация `offset/limit` подтверждена.
- **Персонализация**: публичный фид — общий каталог, не персональная подборка под резюме владельца (та живёт за `/api/vacancies`, требует логина — 401). Для MVP это приемлемо и даже уместно: релевантность считает наш RELEVANCE-контекст против резюме EM, персонализация GetMatch не нужна. Авторизованный персональный фид — опциональный хвост (research §5), в scope этапа 4 НЕ входит.
- Поля JSON зафиксированы golden'ом обезличенного реального ответа; реальные значения (компании, тексты) — данные владельца/публичные, обезличиваются в golden.

## Out of Scope

- Авторизованный персональный фид `/api/vacancies` (нужен логин; опциональный хвост, research §5).
- userbot/Telethon чтение бота GetMatch (заблокирован, как HH — api_id не создаётся).
- Playwright-парсинг HTML `/vacancies` (не нужен — есть JSON; и гейтился бы железом).
- Ежедневное «поднятие» профиля в GetMatch (PLAN упоминает `ResumePublish` для GetMatch — вынесено: у публичного фида нет действия-записи; поднятие профиля потребует авторизованной сессии — отдельный хвост, не в MVP этапа).
- Изменение домена Sourcing, статусной машины, схемы данных (новых таблиц нет — работает минимальный слой `seen_vacancy`).
