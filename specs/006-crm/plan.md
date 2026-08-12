# Implementation Plan: CRM, хранилище, письма, MCP (Этап 6)

**Branch**: `006-crm` | **Date**: 2026-08-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-crm/spec.md`

## Summary

Финальная фича: полное хранилище `vacancy` (миграция seen/labeled поверх, 6A) → CRM-агрегат `Application` со статусной машиной §3.3 (6B) → аналитика `/stats`/`/costs`/`/review` (6C); параллельно после 6A — семантический few-shot на pgvector (6D) и сопроводительные письма Pro (6E); поверх готовых use cases — MCP-сервер (6F) и HR-извлечение для «➕ собес» (6G). Слои гексагональные: домен `crm`/`correspondence` без I/O, use cases в `application/`, бот и MCP — тонкие интерфейсы. Каждая LLM-задача — версионируемый промпт + pydantic-схема + `llm_call` + eval-датасет.

## Technical Context

**Language/Version / Dependencies / Storage / Testing / Platform**: Python 3.12; +`FastMCP` (6F), +`hypothesis` (property-тесты 6B); pgvector уже в стеке (колонка `vector(768)` есть). Хранилище — PostgreSQL 16 + pgvector, миграции 0007–0010 (research §7, чейнятся поверх stage-5 head `0006_stage5`). Тесты — пирамида constitution II: unit(property) → contract(fake LLM) → integration(testcontainers/БД) → eval.

**Constraints**: миграция без потерь (S1/S2/R1 сохранены); тела писем/HR-сообщений не логируются (M4); отправка писем только вручную (VI); MCP — auth-токен + туннель + read-роль (IV); модели только из конфига (III); CI-eval в fake-режиме без ключей.

**Scale/Scope**: single-owner, тысячи вакансий; ≤50 карточек/день; письма/собесы — единицы в день.

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Слои | `domain/crm/` (статусная машина — методы агрегата, не if-ы в боте), `domain/correspondence/` (CoverLetter); use cases в `application/`; `app/mcp/` и бот — тонкие; import-linter контракт для `app/mcp` ([P-C2]) | PASS |
| II. Test-first | Property-тесты статусной машины [C-U1]–[C-U3] красными до кода; [F-I1] миграция; [C-I1]/[C-I2] integration; eval `cover_letter`/`hr_extract`/[R-E2] | PASS |
| III. LLM | Новые промпты `letter_v1`, `hr_extract_v1`; схемы `CoverLetterOut`/`HrDetails`; `EmbeddingPort`; модели из конфига (`LLM_MODEL_LETTERS`/`_JUDGE`/`_EMBEDDING`); стабы для fake; `llm_call` (O1) | PASS |
| IV. Безопасность | Тела писем/HR не логируются (M4); секреты из env; MCP auth-токен + туннель + read-роль + белый список write; тексты вакансий/писем — недоверенные данные | PASS |
| V. Наблюдаемость | Каждый LLM-вызов → `llm_call` + Langfuse; use cases — OTel child spans; `/costs` сверяется с Langfuse ±5% | PASS |
| VI. Человек в контуре | Отправка писем — только вручную; «➕ собес» не меняет статус автоматически (C3); MCP write — только `{set_status, run_digest(dry_run)}` | PASS |

## Project Structure

```text
app/
├── domain/
│   ├── crm/                     # NEW (6B): Application, ApplicationStatus, RejectStage,
│   │                            #   InterviewRound(kind, ordinal), IllegalTransition, события §3.3
│   └── correspondence/          # +CoverLetter (6E), HrDetails (6G)
├── ports/
│   ├── repositories.py          # +VacancyRepositoryPort (6A), ApplicationRepositoryPort (6B),
│   │                            #   CoverLetterRepositoryPort (6E), EmbeddingPort (6D)
│   └── mcp.py                   # NEW (6F): реестр инструментов + флаг write
├── adapters/
│   ├── persistence/
│   │   ├── models.py            # SeenVacancy→Vacancy (+raw/duplicate_of/canary, 6A);
│   │   │                        #   +Application/InterviewRound (6B), +CoverLetter (6E)
│   │   ├── repositories.py      # ретаргет на vacancy (6A); +Application/CoverLetter repos
│   │   └── alembic/versions/    # 0007..0010 (research §7)
│   ├── llm/
│   │   ├── prompts/             # +letter_v1.md (6E), +hr_extract_v1.md (6G)
│   │   ├── fake.py              # +stub_letter_response, stub_hr_response, fake embeddings
│   │   └── embeddings_openrouter.py  # NEW (6D): EmbeddingPort real
├── application/
│   ├── save_vacancy.py          # NEW (6B): 💾 → Application(new); C1
│   ├── change_status.py         # NEW (6B): переходы/раунды/отказ/удаление
│   ├── add_interview_details.py # NEW (6B ручной / 6G LLM): «➕ собес», C3
│   ├── funnel_stats.py          # NEW (6C): /stats
│   ├── report_costs.py          # NEW (6C): /costs (сверка llm_call)
│   ├── review_agreement.py      # NEW (6C): /review agreement rate
│   ├── generate_cover_letter.py # NEW (6E): ✉️/🔁, Pro, только факты резюме
│   └── (score_vacancy.py)       # 6D: инъекция семантического селектора few-shot
├── bot/                         # +💾/статусы/раунды/🗑/➕собес (6B), /saved /stats /costs /review (6C), ✉️/🔁/✏️ (6E)
├── mcp/                         # NEW (6F): FastMCP-сервер, инструменты поверх use cases
└── runtime/composition.py       # +сборка новых use cases (аддитивно, по под-этапам)

eval/
├── datasets/{cover_letter,hr_extract}/v1.jsonl   # NEW (6E, 6G)
├── runners/{cover_letter.py,hr_extract.py}       # NEW; relevance.py +сравнение селекторов (6D)
└── runners/run.py                                # +диспетчеры cover_letter/hr_extract, THRESHOLDS

tests/
├── unit/domain/test_crm.py             # property [C-U1]–[C-U3]
├── unit/domain/test_cover_letter.py    # схема/лимит (6E)
├── contract/test_save_vacancy.py, test_change_status.py, test_generate_letter.py
├── integration/test_migration_0007.py  # [F-I1] backfill без потерь
├── integration/test_crm_flow.py        # [C-I1] полный цикл через бот-хендлеры
├── integration/test_costs.py           # [C-I2]
└── mcp/test_whitelist.py, test_auth.py, test_layers.py   # [P-U1],[P-C1],[P-C2],[P-I1],[P-I2]
```

**Structure Decision**: зеркало предыдущих этапов; новые домены `crm` (6B) и расширение `correspondence` (6E/6G); MCP — новый интерфейсный слой рядом с ботом. Стабы новых LLM-задач — фабрики в `adapters/llm/fake.py` (паттерн scoring/mail/invite).

## Порядок под-этапов и зависимости

```
6A (vacancy + миграция)  ← фундамент, первым
   ├── 6B (CRM Application) ────┬── 6C (аналитика /stats /costs /review)
   │                            └── 6G (hr_extract → ➕собес)
   ├── 6D (pgvector few-shot)   — параллельно 6B/6E
   └── 6E (cover letters)       — параллельно 6B/6D
6F (MCP) ← после 6A + 6B + 6C (обёртка над их use cases)
```

- **Строгие зависимости**: 6A → всё; 6B → 6C, 6G; {6A,6B,6C} → 6F.
- **Параллелизуемо после 6A**: ветка CRM (6B→6C→6G) ∥ 6D ∥ 6E. Конфликты по `models.py`/`composition.py`/`config.py` — аддитивные, разрешаются тривиально; номера миграций зафиксированы (research §7).
- **Рекомендуемый порядок мержа**: 6A → 6B → 6C → 6D → 6E → 6F → 6G (линейная цепочка миграций 0007→0010; 6C/6F/6G без миграций). При параллельной готовности 6D/6E раньше 6B — оркестратор правит down_revision при мерже (цепочка линейна).

## Точки интеграции с существующим кодом

- **6A**: `models.py` `SeenVacancy`→`Vacancy`; `repositories.py` `SeenVacancyRepository` ретаргет на `vacancy` (порты не меняются); `composition.py` — без изменений семантики скоринга/дайджеста; миграция 0007 (поверх stage-5 head).
- **6B**: `composition.py` +`save_vacancy`/`change_status`/`add_interview_details`; бот — новые кнопки/колбэки `crm:*` и `/saved`; репозиторий Application поверх `vacancy.id`.
- **6C**: читает `llm_call` (уже есть), `application` (6B), `labeled_vacancy` (для `/review`); `report_costs` сверяется с Langfuse-экспортом.
- **6D**: `score_vacancy.py` — селектор few-shot за портом (семантический ∥ «последние N»); `LabelRepository` +метод `nearest(embedding, k)`; `EmbeddingPort` + адаптер; backfill-джоб эмбеддингов; `eval/runners/relevance.py` +сравнение.
- **6E**: `correspondence` +`CoverLetter`; `generate_cover_letter` (модель `LLM_MODEL_LETTERS`); бот кнопка «✉️» на карточке + «🔁»/«✏️»; читает `resumes/` (резюме EM + рекомендации); eval `cover_letter`.
- **6F**: `app/mcp/` поверх use cases 6A/6B/6C + `run_digest`; `ports/mcp.py` реестр; import-linter контракт; ops-скрипт роли `mcp_ro`.
- **6G**: `add_interview_details` +LLM-путь (`hr_extract`); стаб + eval.

## Сверка с DOMAIN.md / TEST_CASES.md

- Термины §3.1/§3.3/§3.4/§3.7 дословно: `Vacancy`, `Application(status, interview_rounds[], reject_stage?, interview_url?, notes)`, `ApplicationStatus`, `InterviewRound`, `RejectStage`, `CoverLetter`, MCP-инструмент; инварианты C1–C3, M3–M4, MCP1–MCP4.
- Кейсы: раздел 5 CRM ([C-U1]–[C-U5], [C-I1], [C-I2], [C-E1], [C-E2]); раздел 6 MCP ([P-U1], [P-C1], [P-C2], [P-I1], [P-I2]); [R-E2] pgvector; [M-C3]/[M-E2] письма; [F-I1] миграция; [R-U5] R1.
- §4: `vacancy`/`application`(+`interview_round`)/`cover_letter` — миграции по одной на под-этап; время UTC.
- §5 «Как расширять домен»: новый статус — только через DOMAIN.md + property-тесты (в этом этапе статусы уже зафиксированы §3.3); новая LLM-задача — метод порта + промпт + датасет + метрика; новый MCP-инструмент — обёртка над use case, write — только расширением белого списка.
