# Data Model: Этап 6 (миграции 0007–0010)

Время в БД — UTC (timestamptz). Домен — без ORM; конверсия ORM↔домен в `repositories.py`.

## Обзор миграций (research §7)

⚠️ Номера чейнятся поверх stage-5 head (`0006_stage5`, в работе; stage 4 миграцию не добавлял). При перенумерации stage-5 при мерже — оркестратор ребейзит down_revision первой миграции этапа 6.

| Миграция | Под-этап | down_revision |
|---|---|---|
| `0007_stage6a_vacancy` | 6A | `0006_stage5` (stage-5 head) |
| `0008_stage6b_application` | 6B | `0007_stage6a_vacancy` |
| `0009_stage6d_pgvector` | 6D | `0008_stage6b_application` |
| `0010_stage6e_cover_letter` | 6E | `0009_stage6d_pgvector` |

---

## 1. `vacancy` (0007, под-этап 6A) — полное хранилище

Стратегия: **rename `seen_vacancy` → `vacancy` + additive-колонки + backfill** (research §1). `id` сохраняется — на него сошлётся `application.vacancy_id`. Индексы `seen_vacancy` (uq `source_ref`, `normalized_key`) переезжают с таблицей.

| Колонка | Тип | Ограничения / примечание |
|---|---|---|
| id | bigserial | PK (сохранён из seen_vacancy) |
| source_ref | text | NOT NULL, **UNIQUE** (S1) |
| content_hash | text | NOT NULL |
| normalized_key | text | NOT NULL, index (S2) |
| first_seen_at | timestamptz | NOT NULL |
| digest_sent_at | timestamptz | NULL |
| title / company / url | text | NULL — снапшот карточки |
| description_text | text | NULL — очищен от HTML (S3) |
| salary_from / salary_to | integer | NULL |
| salary_currency | text | NULL |
| score / score_reason | integer / text | NULL — R1 |
| prompt_version / score_model | text | NULL — R1 (не скорить повторно той же версией) |
| scored_at | timestamptz | NULL |
| **raw** | jsonb | **NEW** NOT NULL DEFAULT `'{}'`; backfill историков = `{"description": description_text}`; новые пишут полный `raw` (`Vacancy.create`, S3) |
| **duplicate_of** | text | **NEW** NULL — SourceRef оригинала (S2); историки NULL |
| **canary** | bool | **NEW** NOT NULL DEFAULT false — вакансия из canary-источника |

**Инварианты, сохранённые миграцией**: S1 (uq source_ref), S2 (normalized_key + duplicate_of), R1 (score/prompt_version), S3 (description_text/raw). Тест [F-I1]: `vacancy`.count == `seen_vacancy`.count до миграции; повторный upgrade идемпотентен; uq работает.

**`labeled_vacancy`** — без изменений в 0007 (остаётся снапшотами размеченных; `embedding vector(768)` уже есть, наполняется в 6D). Опциональная связь `labeled_vacancy.source_ref → vacancy.source_ref` — логическая, FK не обязателен (labeled может пережить чистку vacancy).

### Домен (app/domain/sourcing) — 6A
`Vacancy` уже содержит `raw`, `duplicate_of`, `salary`, снапшот (`vacancy.py`). Добавить признак `canary: bool = False`. Порт `VacancyRepositoryPort` — надстройка над существующими методами `SeenVacancyRepository` (сигнатуры не меняются; класс/таблица переименованы).

---

## 2. `application` + `interview_round` (0008, под-этап 6B) — CRM

### Домен (app/domain/crm, без ORM)

| Объект | Тип | Поля / правила (§3.3) |
|---|---|---|
| `ApplicationStatus` | StrEnum | `new` → `applied` → `interview` → `offer` \| `rejected` (только вперёд) |
| `RejectStage` | StrEnum | `pre_hr`, `hr`, `tech`, `final` |
| `InterviewRoundKind` | StrEnum | `hr`, `tech-1`, `tech-2`, …, `final` (упорядочены) |
| `InterviewRound` | VO | `kind`, `ordinal`, `at` — строго по возрастанию (C2, [C-U2]) |
| `Application` | агрегат | `vacancy_id`, `status`, `interview_rounds[]`, `reject_stage?`, `interview_url?`, `notes`; методы `apply/to_interview/add_round/to_offer/reject/add_interview_details` |
| `IllegalTransition` | ошибка | недопустимый переход (C2); единое имя с networking §3.3 |

**Правила статусной машины (единственный источник — §3.3):**
- переходы только вперёд; назад → `IllegalTransition` ([C-U1]);
- раунды добавляются только в статусе `interview`, строго по возрастанию ([C-U2]);
- `reject(stage)`: из `new`/`applied` → `stage ∈ {pre_hr, hr}`; из `interview` → `stage ∈ {hr, tech, final}`; stage обязателен ([C-U3]);
- `add_interview_details(url?, notes?)` — дополняет поля, статус НЕ меняет (C3, [C-U5]);
- удаление Application — из любого статуса (не переход).

### Таблицы (0008)

`application`:

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| vacancy_id | bigint | NOT NULL, FK → vacancy(id), **UNIQUE** (C1 — один активный; удаление = DELETE) |
| status | text | NOT NULL CHECK ∈ (new, applied, interview, offer, rejected) |
| reject_stage | text | NULL CHECK ∈ (pre_hr, hr, tech, final); NOT NULL когда status=rejected (CHECK) |
| interview_url | text | NULL |
| notes | text | NULL |
| created_at / updated_at | timestamptz | NOT NULL default now() |

`interview_round`:

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| application_id | bigint | NOT NULL, FK → application(id) ON DELETE CASCADE |
| kind | text | NOT NULL (hr, tech-1, …, final) |
| ordinal | int | NOT NULL — монотонность в пределах application |
| at | timestamptz | NOT NULL default now() |
| | | UNIQUE(application_id, ordinal), UNIQUE(application_id, kind) |

### Порт `ApplicationRepositoryPort`
`get_by_vacancy(vacancy_id) -> Application|None`, `save(app) -> id`, `delete(vacancy_id)`, `list_all() -> list[Application]` (для `/saved`), `funnel_counts() -> dict[status,int]` (для `/stats`).

---

## 3. pgvector-индекс (0009, под-этап 6D)

Только индекс (колонка `embedding vector(768)` уже существует):
```
CREATE INDEX ix_labeled_embedding_hnsw ON labeled_vacancy
  USING hnsw (embedding vector_cosine_ops);
```
HNSW cosine — малый объём, без обучения списков (research §3). Наполнение эмбеддингов — идемпотентный backfill-джоб (LLM-вызовы в миграции запрещены).

### Порт/домен — 6D
- `EmbeddingPort.embed(text) -> list[float]` (768); адаптер `embeddings_openrouter` + fake.
- `LabelRepositoryPort` +`nearest(embedding, k) -> list[LabeledVacancy]` (`ORDER BY embedding <=> :q LIMIT k`).
- Селектор few-shot — стратегия: `SemanticSelector` (nearest) ∥ `RecentSelector` (текущий `recent`); фолбэк на recent при `< FEWSHOT_MIN_EMBEDDED`.

---

## 4. `cover_letter` (0010, под-этап 6E)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| vacancy_id | bigint | NOT NULL, FK → vacancy(id) |
| text | text | NOT NULL, CHECK char_length ≤ 2000 (M3) |
| prompt_version | text | NOT NULL |
| created_at | timestamptz | NOT NULL default now() |

Несколько версий письма на вакансию допустимы (🔁 создаёт новую строку; последняя — актуальная). Тела писем — данные владельца в его БД (не логи, M4).

### Домен (app/domain/correspondence) — 6E
`CoverLetter(vacancy_id, text ≤2000, prompt_version)`; схема LLM `CoverLetterOut(text: str<=2000)`. Порт `CoverLetterRepositoryPort`: `add(letter) -> id`, `latest(vacancy_id) -> CoverLetter|None`.

---

## 5. HR-детали (под-этап 6G) — без миграции

Пишет в существующие `application.interview_url`/`notes` (0008). Домен `correspondence`: `HrDetails(date: date|None, url: str|None, gist: str<=200)`; схема LLM одноимённая. Заполняется через `add_interview_details` (второй путь — LLM `hr_extract`), статус не трогает (C3).

---

## 6. MCP-роль Postgres (под-этап 6F) — ops, не alembic

Роль `mcp_ro` с `GRANT SELECT` на read-таблицы (`vacancy`, `application`, `interview_round`, `llm_call`, `labeled_vacancy`) — создаётся деплой-скриптом (`CREATE ROLE`/`GRANT` — инфраструктурный шаг, не миграция схемы). Read-инструменты MCP ходят под `MCP_DB_DSN` (`mcp_ro`); write-инструменты (`set_status`, `run_digest`) — через основной пул приложения. Тест [P-I1]: запись под read-ролью → ошибка прав БД.
