# Tasks: CRM, хранилище, письма, MCP (Этап 6)

**Input**: Design documents from `/specs/006-crm/`

**Tests**: обязательны (constitution II): красный тест по кейсу TEST_CASES.md (разделы 5–6, [F-I1], [R-E2], [M-C3]/[M-E2], [R-U5]) — до кода.

## Format: `[ID] [P?] [Story] Description`

`[P]` — можно параллелить (разные файлы/под-этапы). Префикс задачи = под-этап (T6A…T6G).

---

## Под-этап 6A — Полное хранилище `vacancy` + миграция (фундамент)

> Зависимости: нет. Блокирует всё. Миграция `0007_stage6a_vacancy` (down_revision `0006_stage5` — stage-5 head; ребейз при мерже, research §7).

- [x] **T6A-1** [F-I1] Красный integration-тест миграции `0007`: на фикстуре `seen_vacancy` (N строк + labeled M) после `upgrade` → таблица `vacancy` содержит N строк, `source_ref`/`content_hash`/`normalized_key`/скор/снапшот целы; `vacancy`.count == N; повторный `upgrade` идемпотентен; `downgrade`→`upgrade` данные целы. → tests/integration/test_migration_0007.py
- [x] **T6A-2** Миграция `0007_stage6a_vacancy`: rename `seen_vacancy`→`vacancy`; add `raw jsonb NOT NULL DEFAULT '{}'`, `duplicate_of text NULL`, `canary bool NOT NULL DEFAULT false`; backfill `raw = jsonb_build_object('description', description_text)` для историков; индексы (uq `source_ref`, `normalized_key`) переезжают (data-model §1). down_revision=`0006_stage5` (stage-5 head).
- [x] **T6A-3** [S-U1][S-U2][R-U5] ORM `SeenVacancy`→`Vacancy` в models.py (+raw/duplicate_of/canary); домен `Vacancy` +`canary: bool = False`; `SeenVacancyRepository` ретаргет на `vacancy` (сигнатуры портов не меняются). Регресс-тесты дедупа/скоринга (S1/S2/R1) зелёные на новой таблице.
- [x] **T6A-4** `VacancyRepositoryPort` (ports/repositories.py): `get(source_ref)`, `get_by_id(id)`, `list(filter)`, `search_saved(query)` — для CRM/MCP/аналитики; contract-тест на fake. Композиция: `composition.py` без изменения семантики дайджеста.

**Выход 6A**: `vacancy` в проде, данные не потеряны, инварианты держатся; репозиторий доступен CRM/аналитике/MCP. **Приёмка**: SC-001.

---

## Под-этап 6B — CRM: агрегат `Application` 🎯 ядро

> Зависимости: 6A. Миграция `0008_stage6b_application` (down_revision `0007`).

- [x] **T6B-1** [C-U1] Property-тест (`hypothesis`) статусной машины §3.3: перебор всех пар `(from,to)` — допустимы только переходы §3.3, остальные → `IllegalTransition`, состояние неизменно (C2). → tests/unit/domain/test_crm.py
- [x] **T6B-2** [C-U2] Property-тест раундов: добавление только в `interview`, строго по возрастанию; повтор `hr`/`tech-1` → ошибка порядка; `tech-2` → ок.
- [x] **T6B-3** [C-U3] Тест отказа: из `new`/`applied` → `stage ∈ {pre_hr,hr}`; из `interview` → `{hr,tech,final}`; `reject` без stage → ошибка.
- [x] **T6B-4** Домен `app/domain/crm/` (зелёный по T6B-1..3): `ApplicationStatus`, `RejectStage`, `InterviewRoundKind`, `InterviewRound`, агрегат `Application` (методы `apply/to_interview/add_round/to_offer/reject/add_interview_details`), `IllegalTransition`, события `VacancySaved`/`StatusChanged`/`InterviewScheduled` (§3.3).
- [x] **T6B-5** Миграция `0008_stage6b_application`: `application` (uq `vacancy_id` — C1; CHECK статусов/reject_stage) + `interview_round` (FK CASCADE, uq(app,ordinal), uq(app,kind)); ORM + `ApplicationRepository` (data-model §2). Integration-тест схемы.
- [x] **T6B-6** [C-U4] Contract-тест → `application/save_vacancy.py`: 💾 создаёт `Application(new)` + `VacancySaved`; повтор 💾 → тот же Application (C1), дубль не создан.
- [x] **T6B-7** Contract-тесты → `application/change_status.py`: переходы/раунды/отказ/удаление через доменные методы; недопустимый → `IllegalTransition` (без изменения состояния).
- [x] **T6B-8** [C-U5] Contract-тест → `application/add_interview_details.py` (ручной путь): «➕ собес» дополняет `interview_url`/`notes`, статус НЕ меняет (C3). LLM-путь — 6G.
- [x] **T6B-9** [C-I1] Integration: бот-хендлеры (aiogram harness) — карточка → 💾 → applied → interview(hr) → interview(tech-1) → offer; кнопки/колбэки `crm:*`, `/saved`, «🗑», «➕ собес»; DRY_RUN-нейтрально (CRM — локальные записи). Композиция use cases в `composition.py`.

**Выход 6B**: полный цикл заявки через бот. **Приёмка**: SC-002.

---

## Под-этап 6C — Аналитика: `/stats`, `/costs`, `/review`

> Зависимости: 6B (для `/stats` нужна воронка Application). Миграции нет.

- [x] **T6C-1** Contract-тест → `application/funnel_stats.py`: воронка Application (счётчики по статусам + конверсии) из `ApplicationRepository.funnel_counts`; бот `/stats`.
- [x] **T6C-2** [C-I2] Integration-тест → `application/report_costs.py`: `/costs` за период = сумма `llm_call.cost_usd` (фикстуры) и сверка с Langfuse-экспортом ±5%; бот `/costs`.
- [x] **T6C-3** [C-E2] Contract/integration → `application/review_agreement.py`: `/review` — N случайных скоренных вакансий → вердикты владельца → agreement rate в отчёт; расхождения записаны в `label` (через `LabelRepository.upsert`). Бот `/review` (пошаговый диалог).

**Выход 6C**: измеримость воронки/затрат/качества. **Приёмка**: SC-003.

---

## Под-этап 6D — Семантический few-shot selector (pgvector)

> Зависимости: 6A. Параллельно 6B/6E. Миграция `0009_stage6d_pgvector`.

- [x] **T6D-1** `EmbeddingPort.embed(text)->list[float]` (768) + fake (детерминированный) + `embeddings_openrouter` (модель `LLM_MODEL_EMBEDDING`, `llm_call` purpose=`embedding`, O1); contract-тест.
- [x] **T6D-2** Миграция `0009_stage6d_pgvector`: HNSW-индекс `hnsw (embedding vector_cosine_ops)` на `labeled_vacancy` (data-model §3). Integration-тест наличия индекса.
- [x] **T6D-3** `LabelRepository.nearest(embedding, k)` (`<=>` cosine) + запись embedding при разметке; идемпотентный backfill-джоб эмбеддингов историков (не миграция). Contract/integration-тест.
- [x] **T6D-4** Селектор few-shot как стратегия: `SemanticSelector` ∥ `RecentSelector`; инъекция в `score_vacancy.py`; фолбэк на recent при `< FEWSHOT_MIN_EMBEDDED` ([R-U2]-совместимо). Unit/contract-тест выбора и фолбэка.
- [x] **T6D-5** [R-E2] **Eval-задача**: расширить `eval/runners/relevance.py` — сравнение семантического селектора vs «последние N» на датасете `relevance`; метрика agreement rate/F1; **порог: семантический ≥ базового**; отчёт с двумя строками в `eval/reports/`. `make eval CONTEXT=relevance` (переключатель селектора). *(shipped: раннер+датасет+отчёт `eval/reports/relevance_selectors_2026-08-12.md`, CI-eval fake=PASS; pending: содержательное real-сравнение селекторов на OpenRouter)*

**Выход 6D**: семантический few-shot + доказательство неухудшения. **Приёмка**: SC-004.

---

## Под-этап 6E — Сопроводительные письма (Pro)

> Зависимости: 6A. Параллельно 6B/6D. Миграция `0010_stage6e_cover_letter`.

- [x] **T6E-1** Домен `correspondence` +`CoverLetter(vacancy_id, text ≤2000, prompt_version)`; схема LLM `CoverLetterOut(text: str<=2000)`; unit-тест лимита/схемы.
- [x] **T6E-2** Миграция `0010_stage6e_cover_letter`: `cover_letter` (FK vacancy, CHECK ≤2000) + `CoverLetterRepository` (data-model §4). Integration-тест схемы.
- [x] **T6E-3** Промпт `letter_v1.md` (русский, «только факты из резюме», ≤2000, текст вакансии — недоверенные данные, R5) + `stub_letter_response` в `adapters/llm/fake.py`.
- [x] **T6E-4** [M-C3] Contract-тест → `application/generate_cover_letter.py`: «✉️» — промпт содержит резюме EM и рекомендации из `resumes/`, русский; модель `LLM_MODEL_LETTERS` (Pro); невалидно → 1 retry → graceful; `llm_call` (O1); persist в `cover_letter`. Бот: «✉️» на карточке, «🔁» (новая версия), «✏️» (ручная правка); отправка только вручную (M3, VI). Тела писем не логируются (M4).
- [x] **T6E-5** [M-E2] **Eval-задача** `cover_letter`: датасет `eval/datasets/cover_letter/v1.jsonl` (≥10 вакансий) + раннер `eval/runners/cover_letter.py` + диспетчер в `run.py` (+THRESHOLDS): LLM-судья fact-check каждого факта против резюме → **hallucinations=0 (блокер)** + рубрика (обращение к вакансии, 1–2 метрики, ≤2000, без канцелярита); судья `LLM_MODEL_JUDGE`, инфра-сбои судьи вне знаменателя. CI-eval в fake-режиме; real — после OpenRouter. *(shipped: раннер+датасет+отчёт `eval/reports/cover_letter_2026-08-12.md`, CI-eval fake=PASS; pending: real fact-check прогон на OpenRouter)*

**Выход 6E**: письма Pro без галлюцинаций, отправка вручную. **Приёмка**: SC-005.

---

## Под-этап 6F — MCP-сервер (FastMCP)

> Зависимости: 6A + 6B + 6C. Схему не меняет (роль `mcp_ro` — ops-скрипт).

- [x] **T6F-1** [P-C2] Import-linter контракт + арх-тест: `app/mcp/` не импортирует `app.adapters.persistence`/SQLAlchemy — только `application/` (MCP1). → tests/mcp/test_layers.py
- [x] **T6F-2** [P-U1] `ports/mcp.py` — реестр инструментов с флагом `write`; фабрика падает при регистрации write вне `{set_status, run_digest}` (MCP2); тест перебирает все зарегистрированные. → tests/mcp/test_whitelist.py
- [x] **T6F-3** [P-C1] `app/mcp/` FastMCP-сервер (stdio, research §4): обязательный `MCP_AUTH_TOKEN` — запрос без/с неверным токеном → отказ до вызова инструмента (MCP3). → tests/mcp/test_auth.py
- [x] **T6F-4** Read-инструменты поверх use cases: `list_vacancies`, `get_vacancy`, `search_saved`, `get_costs`, `funnel_stats` (6A/6C); write: `set_status` (6B `change_status`), `run_digest(dry_run)` (существующий). Contract-тесты каждого инструмента.
- [x] **T6F-5** [P-I1][P-I2] Integration: read-роль `mcp_ro` (ops-скрипт деплоя + запись в quickstart/env) — запись мимо белого списка → ошибка прав БД ([P-I1]); `run_digest(dry_run=true)` → «ТЕСТ», внешних записей нет; `set_status` проходит статусную машину, недопустимый переход отвергнут как [C-U1] ([P-I2]). Compose profile `mcp`.

**Выход 6F**: MCP из Claude Desktop через туннель. **Приёмка**: SC-006.

---

## Под-этап 6G — HR-извлечение (`hr_extract`)

> Зависимости: 6B (плумбинг «➕ собес»). Миграции нет.

- [x] **T6G-1** Домен `correspondence` +`HrDetails(date: date|None, url: str|None, gist: str<=200)`; схема LLM одноимённая; unit-тест схемы.
- [x] **T6G-2** [C-U5] Промпт `hr_extract_v1.md` (текст HR — недоверенные данные, не меняет статус — C3) + `stub_hr_response`; contract-тест → `add_interview_details` LLM-путь: извлечённые дата/ссылка/суть дополняют `interview_url`/`notes`, статус НЕ меняется; `llm_call` (O1); тело сообщения не логируется (M4).
- [x] **T6G-3** [C-E1] **Eval-задача** `hr_extract`: датасет `eval/datasets/hr_extract/v1.jsonl` (≥15 обезличенных HR-сообщений → эталон `{date,url,gist}`) + раннер `eval/runners/hr_extract.py` + диспетчер в `run.py` (+THRESHOLDS): **accuracy по дате и ссылке ≥0.9**. CI-eval в fake-режиме; real — после OpenRouter.

**Выход 6G**: автозаполнение собес-деталей. **Приёмка**: SC-007.

---

## Финал этапа

- [x] **T6-DoD** Гейты зелёные (ruff/mypy/import-linter/pytest; CI-eval fake=PASS); отчёт по DoD PLAN.md §6.
- [ ] **T6-Manual** 🖐 Владелец: первый `/review` (базовый agreement rate), 5 писем на проверку фактов, диалоговый запрос через MCP (SC-008). *(pending: owner-side ручная проверка — артефакта прогона нет)*

## Dependencies

```
6A ─┬─ 6B ─┬─ 6C ─┐
    │       └─ 6G  │
    ├─ 6D          ├─ 6F (нужны 6A+6B+6C)
    └─ 6E          │
```
Порядок мержа (линейная цепочка миграций 0007→0010): 6A → 6B → 6C → 6D → 6E → 6F → 6G. 6D/6E могут разрабатываться параллельно ветке CRM после 6A; при мерже раньше 6B — оркестратор правит down_revision.

## Соответствие кейсам TEST_CASES.md (разделы 5–6 и др.)

| Кейс | Задача |
|---|---|
| [F-I1] | T6A-1, T6A-2 |
| [S-U1][S-U2][R-U5] | T6A-3 |
| [C-U1] | T6B-1 |
| [C-U2] | T6B-2 |
| [C-U3] | T6B-3 |
| [C-U4] | T6B-6 |
| [C-U5] | T6B-8, T6G-2 |
| [C-I1] | T6B-9 |
| [C-I2] | T6C-2 |
| [C-E2] | T6C-3 |
| [R-E2] | T6D-5 |
| [M-C3] | T6E-4 |
| [M-E2] | T6E-5 |
| [P-U1] | T6F-2 |
| [P-C1] | T6F-3 |
| [P-C2] | T6F-1 |
| [P-I1][P-I2] | T6F-5 |
| [C-E1] | T6G-3 |
