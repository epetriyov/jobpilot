# Feature Specification: CRM, хранилище, письма, MCP (Этап 6, финальная фича)

**Feature Branch**: `006-crm`

**Created**: 2026-08-12

**Status**: Draft

**Input**: PLAN.md §6 «Этап 6»: полное хранилище `vacancy` (миграция: seen/labeled поверх него); агрегат Application (💾 Сохранить, `/saved`, статусы+раунды+этапы отказа, 🗑, «➕ собес» — извлечение даты/ссылки из пересланного HR-сообщения, статус не меняет); `/stats`, `/costs`, `/review` (agreement rate); семантический few-shot selector (pgvector) + сравнительный eval против «последних N»; сопроводительные письма (Pro, русский, только факты из резюме, 🔁/✏️, отправка вручную); MCP-сервер по §4. Eval: property-тесты статусной машины; `hr_extract` ≥0.9; `cover_letter` — hallucinations=0 (блокер) + рубрика; сравнение селекторов.

## Декомпозиция на под-этапы *(обязательно — этап очень большой)*

Этап разрезан на 7 под-этапов; префиксы задач — `T6A`…`T6G`. Порядок и зависимости — в plan.md §«Порядок под-этапов».

| ID | Под-этап | Суть | Зависит от |
|---|---|---|---|
| 6A | Хранилище `vacancy` + миграция | Полное `vacancy` (superset seen + raw/duplicate_of/canary), backfill без потерь, инварианты S1/S2/R1 сохранены | — (фундамент) |
| 6B | CRM: агрегат `Application` | Статусная машина §3.3 (property-тесты), 💾 Сохранить, `/saved`, статусы+раунды+этапы отказа, 🗑, «➕ собес» (ручной ввод) | 6A |
| 6C | Аналитика | `/stats` (воронка), `/costs` (сверка с `llm_call` ±5%), `/review` (agreement rate) | 6B |
| 6D | Семантический few-shot (pgvector) | `EmbeddingPort`, заполнение `labeled_vacancy.embedding`, индекс, семантический подбор, сравнительный eval [R-E2] | 6A |
| 6E | Сопроводительные письма | `CoverLetter` (Pro, русский, только факты резюме), ✉️/🔁/✏️, отправка вручную, eval `cover_letter` hallucinations=0 | 6A |
| 6F | MCP-сервер | FastMCP поверх use cases: read + белый список write, auth-токен, туннель, read-роль БД | 6A, 6B, 6C |
| 6G | HR-извлечение | `hr_extract`: дата/ссылка/суть из пересланного HR-сообщения → дополняет «➕ собес»; eval ≥0.9 | 6B |

6D и 6E независимы от CRM-ветки (6B/6C) и могут вестись параллельно с ней после 6A.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Полное хранилище вакансий (Priority: P1, под-этап 6A)

Владелец не теряет ни одной ранее виденной или размеченной вакансии: минимальный слой (`seen_vacancy`/`labeled_vacancy`) переезжает в полноценное хранилище `vacancy`, поверх которого работают CRM, аналитика и письма. Дедуп (S1/S2) и правило «не скорить дважды» (R1) продолжают работать без изменения поведения.

**Why this priority**: фундамент этапа — на `vacancy` ссылаются Application, письма, MCP.

**Independent Test**: `alembic upgrade head` на копии боевой БД → число вакансий в `vacancy` = числу строк `seen_vacancy` до миграции; ежедневный дайджест и `/train` работают как раньше.

**Acceptance Scenarios**:
1. **Given** боевая БД с N строк `seen_vacancy` и M строк `labeled_vacancy`, **When** миграция 0007, **Then** `vacancy` содержит N записей, ни одна не потеряна, `source_ref`/`content_hash`/скор/снапшот сохранены ([F-I1]).
2. **Given** повторное обнаружение вакансии после миграции, **Then** дубликат не создаётся (S1), first_seen не меняется ([S-U1]).
3. **Given** кросс-источниковый повтор (company,title) за 30 дней, **Then** `duplicate_of` проставлен, в дайджест не идёт ([S-U2]).
4. **Given** вакансия со скором текущей prompt_version, **Then** повторный LLM-вызов не происходит (R1, [R-U5]).
5. **Given** `alembic downgrade` + `upgrade`, **Then** идемпотентность, данные целы.

---

### User Story 2 — Сохранение вакансии и движение по воронке (Priority: P1, под-этап 6B)

На карточке вакансии владелец жмёт «💾 Сохранить» — создаётся `Application` в статусе `new`. Дальше кнопками двигает статус: `new → applied → interview` (с раундами `hr → tech-1 → … → final`) → `offer` либо `rejected` (с обязательным этапом отказа). `/saved` показывает все заявки с текущим статусом. «🗑» удаляет заявку из любого статуса. Обратные переходы запрещены и вежливо отклоняются.

**Why this priority**: это ядро CRM — то, ради чего собирается хранилище.

**Independent Test** ([C-I1]): карточка → 💾 → `applied` → `interview(hr)` → `interview(tech-1)` → `offer`; повтор 💾 той же вакансии не плодит дубль; `/saved` отражает статус.

**Acceptance Scenarios**:
1. **Given** карточка вакансии, **When** 💾, **Then** `Application(status=new)` создан, событие `VacancySaved`; повтор 💾 → тот же Application (C1, [C-U4]).
2. **Given** `Application(new)`, **When** переход в `applied`→`interview`, **Then** статусы двигаются только вперёд; недопустимый переход → `IllegalTransition`, состояние неизменно (C2, [C-U1]).
3. **Given** `interview` c раундами `[hr, tech-1]`, **When** добавить `hr`/`tech-1` повторно → ошибка порядка; `tech-2` → ок ([C-U2]).
4. **Given** отказ из `applied` → `stage ∈ {pre_hr, hr}`; из `interview` → `stage ∈ {hr, tech, final}`; отказ без stage → ошибка ([C-U3]).
5. **Given** «🗑», **Then** Application удалён из любого статуса (это не переход), вакансия остаётся в `vacancy`.

---

### User Story 3 — Добавление собеса из пересланного HR-сообщения (Priority: P2, под-этапы 6B ручной + 6G авто)

Владелец пересылает боту сообщение HR о собеседовании и жмёт «➕ собес». Система дополняет `interview_url`/`notes` заявки (в 6B — по ручному вводу/ссылке; в 6G — LLM извлекает дату/ссылку/суть из текста). Статус при этом **никогда** не меняется автоматически — только фиксируются детали.

**Why this priority**: удобство подготовки к собесам; не блокирует основную воронку.

**Independent Test**: переслать сообщение с датой и ссылкой → `/saved` показывает у заявки собес-детали; статус прежний ([C-U5]).

**Acceptance Scenarios**:
1. **Given** «➕ собес» с текстом, содержащим дату и ссылку, **When** извлечение, **Then** `interview_url`/`notes` заполнены, статус НЕ изменён (C3, [C-U5]).
2. **Given** HR-сообщение без даты/ссылки, **Then** заполняется `notes` сутью, `interview_url` пуст, ошибки нет.
3. **Given** eval `hr_extract` (≥15 обезличенных сообщений), **Then** accuracy по дате и ссылке ≥0.9 ([C-E1]).

---

### User Story 4 — Аналитика: воронка, затраты, качество подбора (Priority: P2, под-этап 6C)

`/stats` — воронка Application (сколько в каждом статусе, конверсии). `/costs` за период — сумма затрат LLM из `llm_call`, сходится с Langfuse-экспортом ±5%. `/review` — механика измерения agreement rate: N случайных скоренных вакансий → вердикты владельца → доля совпадений со скорингом, расхождения дописываются в `label`.

**Why this priority**: измеримость (constitution V/VI) — но поверх готовых воронки и хранилища.

**Independent Test** ([C-I2]): `/costs` за период = сумма фикстур `llm_call.cost_usd`; `/stats` = корректные счётчики по статусам.

**Acceptance Scenarios**:
1. **Given** заявки в разных статусах, **When** `/stats`, **Then** воронка с числами и конверсиями.
2. **Given** записи `llm_call` за период, **When** `/costs`, **Then** сумма совпадает с фикстурами и с Langfuse ±5% ([C-I2]).
3. **Given** `/review` на 10 скоренных, **When** владелец даёт вердикты, **Then** agreement rate сохранён в отчёт, расхождения записаны в `label` ([C-E2]).

---

### User Story 5 — Семантический few-shot selector (Priority: P2, под-этап 6D)

Скоринг подбирает few-shot-примеры не по «последним N», а по семантической близости (pgvector, эмбеддинги размеченных вакансий). Сравнительный eval показывает, что качество подбора семантического селектора не ниже базового.

**Why this priority**: повышает точность скоринга, но заметная ценность — только на накопленной разметке.

**Independent Test** ([R-E2]): на одном датасете `relevance` agreement rate семантического селектора ≥ базового «последние N»; отчёт в PR.

**Acceptance Scenarios**:
1. **Given** ≥N размеченных вакансий с эмбеддингами, **When** скоринг новой вакансии, **Then** few-shot — семантически ближайшие (R3), при отсутствии эмбеддингов — фолбэк «последние N».
2. **Given** сравнительный прогон, **Then** agreement rate семантического ≥ базового, отчёт приложен ([R-E2]).

---

### User Story 6 — Сопроводительные письма (Priority: P1, под-этап 6E)

По вакансии владелец жмёт «✉️» — генерируется сопроводительное письмо (модель Pro, русский язык), содержащее только факты из резюме EM. Кнопки «🔁 Перегенерировать» и «✏️ Править». Отправка — всегда вручную владельцем (система не отправляет). Eval гарантирует hallucinations=0.

**Why this priority**: одна из двух главных пользовательских ценностей этапа наряду с CRM.

**Independent Test** ([M-C3]): «✉️» → промпт содержит резюме EM и рекомендации из `resumes/`, язык русский; письмо ≤2000 знаков.

**Acceptance Scenarios**:
1. **Given** карточка вакансии, **When** «✉️», **Then** письмо на русском, только факты из резюме, ≤2000 знаков, обращается к вакансии ([M-C3]).
2. **Given** «🔁», **Then** новая версия письма; «✏️» — режим ручной правки; отправка только вручную (M3, constitution VI).
3. **Given** eval `cover_letter` (≥10 вакансий), **Then** LLM-судья: каждый факт письма присутствует в резюме → hallucinations=0 (блокер) + рубрика (обращение к вакансии, 1–2 метрики, ≤2000 знаков, без канцелярита) ([M-E2]).

---

### User Story 7 — MCP-сервер для доступа из Claude Desktop (Priority: P2, под-этап 6F)

Владелец из Claude Desktop через SSH-туннель обращается к данным агента: список/детали вакансий, поиск по сохранённым, затраты, воронка (read), а также белый список write (`set_status`, `run_digest(dry_run)`). Доступ защищён auth-токеном, только localhost/туннель, отдельная read-роль Postgres.

**Why this priority**: диалоговый доступ и подготовка к собесам — ценно, но поверх готовых use cases.

**Independent Test** ([P-I2]): `run_digest(dry_run=true)` через MCP → дайджест «ТЕСТ», внешних записей нет; `set_status` проходит статусную машину и отвергает недопустимый переход как [C-U1].

**Acceptance Scenarios**:
1. **Given** набор зарегистрированных инструментов, **Then** write возможны только у `{set_status, run_digest}`; регистрация write вне списка → ошибка (MCP2, [P-U1]).
2. **Given** запрос без/с неверным auth-токеном, **Then** отказ, инструмент не вызван (MCP3, [P-C1]).
3. **Given** модуль `app/mcp/`, **Then** он не импортирует SQLAlchemy/persistence — только `application/` (MCP1, import-linter, [P-C2]).
4. **Given** read-роль Postgres, **When** запись мимо белого списка, **Then** отказ на уровне прав БД (MCP4, [P-I1]).

---

### Edge Cases

- Миграция на большой БД: `vacancy` наследует индексы `seen_vacancy` (uq `source_ref`, `normalized_key`); backfill в одной транзакции миграции (объём single-owner мал).
- «➕ собес» на вакансию без Application → подсказка «сначала 💾 Сохранить»; статус не трогается.
- Удаление Application → повторное 💾 создаёт новый Application `new` (C1 про активный — прежний удалён).
- Cover letter при недоступном Pro/ключе → LLM_MODE=fake даёт детерминированный стаб (паттерн этапов 1–3); реальный eval `cover_letter` — после подключения OpenRouter (хвост).
- pgvector без накопленной разметки (<порог эмбеддингов) → фолбэк «последние N», без падения ([R-U2]).
- MCP-туннель разорван → бот и worker работают независимо; MCP не критичен для пайплайна.
- HR-сообщение — недоверенные данные: экранируется в промпте, не может менять статус или инициировать действия (R5-аналог, C3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (6A): Система MUST хранить полное `vacancy` (поля §3.1 + `raw jsonb`, `duplicate_of`, `canary`); миграция 0007 переносит `seen_vacancy`/`labeled_vacancy` поверх без потери данных и без изменения инвариантов S1/S2/R1 ([F-I1], [S-U1], [S-U2], [R-U5]).
- **FR-002** (6B): Агрегат `Application` MUST реализовать статусную машину §3.3 как доменные методы (не if-ы в боте): переходы только вперёд, `IllegalTransition` при недопустимом; раунды строго по возрастанию; отказ требует валидного `stage`; один активный Application на вакансию (C1–C3, [C-U1]–[C-U4]).
- **FR-003** (6B): Бот MUST давать кнопки/команды: «💾 Сохранить», `/saved`, кнопки переходов статусов и раундов, «🗑 удалить», «➕ собес»; персист — таблицы `application` (+child `interview_round`).
- **FR-004** (6B/6G): «➕ собес» MUST только дополнять `interview_url`/`notes` и НИКОГДА не менять статус автоматически (C3, [C-U5]); LLM-извлечение (6G) даёт дату/ссылку/суть с eval `hr_extract` accuracy ≥0.9 ([C-E1]).
- **FR-005** (6C): MUST существовать `/stats` (воронка), `/costs` (сумма `llm_call.cost_usd` за период, сверка с Langfuse ±5%), `/review` (agreement rate с записью расхождений в `label`) ([C-I2], [C-E2]).
- **FR-006** (6D): Скоринг MUST выбирать few-shot семантически (pgvector, эмбеддинги `labeled_vacancy`) с фолбэком «последние N»; сравнительный eval [R-E2] — agreement rate семантического ≥ базового, отчёт в PR.
- **FR-007** (6E): `CoverLetter` MUST генерироваться моделью Pro на русском, содержать только факты резюме, ≤2000 знаков; кнопки «🔁»/«✏️»; отправка только вручную (M3); eval `cover_letter` — hallucinations=0 (блокер) + рубрика ([M-C3], [M-E2]).
- **FR-008** (6F): MCP-сервер MUST давать read-инструменты (`list_vacancies`, `get_vacancy`, `search_saved`, `get_costs`, `funnel_stats`) и белый список write (`set_status`, `run_digest(dry_run)`); auth-токен; localhost/туннель; отдельная read-роль Postgres; `app/mcp/` вызывает только `application/` (MCP1–MCP4, [P-U1], [P-C1], [P-C2], [P-I1], [P-I2]).
- **FR-009**: Все новые LLM-задачи (cover letter, hr_extract, embeddings) MUST идти через `LlmPort`/`EmbeddingPort` с версионируемым промптом, pydantic-схемой и записью `llm_call` (O1); тела писем и HR-сообщений не логируются (M4, constitution IV).

### Key Entities

- **Vacancy** (DOMAIN.md §3.1, таблица `vacancy`, миграция 0007): `source_ref` (unique, S1), `content_hash`, `normalized_key`, снапшот (title/company/url/description_text/salary_*), скор (score/reason/prompt_version/model/scored_at, R1), `raw jsonb`, `duplicate_of`, `canary bool`, `first_seen_at`, `digest_sent_at`.
- **Application** (§3.3, таблица `application`, миграция 0008): `vacancy_id` (FK, один активный — C1), `status`, `reject_stage?`, `interview_url?`, `notes`, таймстемпы. Child `interview_round(application_id, kind, ordinal, at)`.
- **CoverLetter** (§3.4, таблица `cover_letter`, миграция 0010): `vacancy_id`, `text`, `prompt_version`, `created_at`.
- **LabeledVacancy.embedding** (уже `vector(768)`): заполняется с 6D; индекс — миграция 0009.
- **MCP-инструмент** (§3.7): обёртка над use case; write — только белый список.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** (6A): миграция на копии боевой БД без потерь; `vacancy`.count == `seen_vacancy`.count; кейсы [F-I1], [S-U1], [S-U2], [R-U5] зелёные.
- **SC-002** (6B): property-тесты статусной машины [C-U1]–[C-U5] зелёные; полный цикл [C-I1] через бот-хендлеры проходит.
- **SC-003** (6C): `/costs` = сумма `llm_call.cost_usd` и Langfuse ±5% ([C-I2]); `/stats` — корректная воронка; `/review` пишет расхождения в `label` ([C-E2]).
- **SC-004** (6D): `make eval CONTEXT=relevance` со сравнением селекторов — agreement rate семантического ≥ базового ([R-E2]).
- **SC-005** (6E): `make eval CONTEXT=cover_letter` — hallucinations=0 (блокер) + рубрика ([M-E2]); 5 писем проверены владельцем.
- **SC-006** (6F): MCP-инструменты работают из Claude Desktop через туннель; [P-U1], [P-C1], [P-C2], [P-I1], [P-I2] зелёные.
- **SC-007** (6G): `make eval CONTEXT=hr_extract` — accuracy по дате и ссылке ≥0.9 ([C-E1]).
- **SC-008**: 🖐 Ручная проверка — первый `/review` (базовый agreement rate), 5 писем на факты, диалоговый запрос через MCP (PLAN.md §6).

## Assumptions

- Объём БД single-owner мал (тысячи вакансий) → миграция 0007 выполняется в одной транзакции в короткое окно (ежедневный дайджест не страдает); стратегия — expand-and-rename (research §1).
- Эмбеддинги — через тот же OpenRouter/LlmPort-семейство (`EmbeddingPort`, модель из конфига `LLM_MODEL_EMBEDDING`, размерность 768 уже заложена в `labeled_vacancy.embedding`).
- Cover letter и hr_extract eval выполняются после подключения реального LLM (OpenRouter); до этого — детерминированные стабы (паттерн этапов 1–3), CI-eval в fake-режиме.
- MCP подключается к Claude Desktop по stdio/SSH-туннелю; наружу порт не публикуется (compose profile `mcp`, UFW только 22 — PLAN.md §4).
- Статусы воронки — ровно из §3.3; расширение статусов — отдельное изменение DOMAIN.md + property-тесты (DOMAIN.md §5).

## Out of Scope

- Автоматическая отправка писем/инвайтов (запрещено constitution VI; только ручная отправка владельцем).
- Автоизменение статуса Application по входящим письмам (C3 — только дополнение деталей).
- Новые источники вакансий (этапы 4–5); MCP write за пределами `{set_status, run_digest}` (MCP2).
- Мульти-пользовательский режим, публичный API, web-UI CRM (только Telegram + MCP).
- Автоматизация LinkedIn (этап 3, N1).
