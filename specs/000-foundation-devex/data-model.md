# Data Model: Фундамент и DevEx (Этап 0)

Минимальный слой хранения по DOMAIN.md §4 (этапы 0–5). Время — UTC (`timestamptz`). Миграция: `0001_foundation` (одна на этап). Расширение `vector` (pgvector) включается в этой миграции.

## Доменные объекты (app/domain, без ORM)

### shared

| Объект | Тип | Поля / правила |
|---|---|---|
| `Source` | StrEnum | `hh`, `getmatch`, `site`, `manual` |
| `SourceRef` | VO (frozen) | `source: Source`, `site_name: str \| None` (обязателен ⇔ source=site), `external_id: str`; каноническая строка `as_key()` — `source[:site_name]:external_id` |
| `Salary` | VO (frozen) | `from_: int \| None`, `to: int \| None`, `currency: str \| None` — все опциональны |
| `PromptVersion` | VO | `purpose: str`, `version: int`, `as_str()` → `scoring_v1` |
| `DomainEvent` | база | `occurred_at: datetime (UTC)` |

### sourcing

| Объект | Тип | Поля / правила |
|---|---|---|
| `Vacancy` | агрегат | `source_ref: SourceRef`, `title`, `company`, `url`, `description_text` (очищен от HTML — S3), `raw: dict` (оригинал), `salary: Salary`, `location: str \| None`, `published_at: datetime \| None` |
| `VacancyDiscovered` | событие | `source_ref`, `occurred_at` |
| `SourceFetchFailed` | событие | `source: str`, `error: str` |
| `normalize_company_title()` | функция | нормализация (company, title) для кросс-дедупа S2: lower, trim, схлопывание пробелов, удаление пунктуации/юр-форм |
| `content_hash(vacancy)` | функция | sha256 канонизированного содержимого — детект изменений |

## Таблицы (adapters/persistence)

### seen_vacancy — реестр виденных (дедуп, S1/S2)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| source_ref | text | UNIQUE, NOT NULL — каноническая строка SourceRef |
| content_hash | text | NOT NULL |
| normalized_key | text | NOT NULL, INDEX — normalize_company_title для S2 (30 дней) |
| first_seen_at | timestamptz | NOT NULL, неизменяемо (S1) |
| digest_sent_at | timestamptz | NULL — когда ушла в дайджест |

### labeled_vacancy — снапшоты размеченных (few-shot, eval)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| source_ref | text | NOT NULL |
| title / company / url | text | NOT NULL |
| description_text | text | NOT NULL — снапшот очищенного текста |
| verdict | text | NOT NULL, CHECK ∈ (`relevant`,`irrelevant`) |
| embedding | vector(768) | NULL — заполняется с этапа 6 |
| created_at | timestamptz | NOT NULL default now() |

### llm_call — учёт LLM-вызовов (инвариант O1)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| purpose | text | NOT NULL — scoring \| letter \| summary \| extract \| judge |
| model | text | NOT NULL — фактическая модель из конфига |
| prompt_version | text | NOT NULL |
| input_tokens / output_tokens | int | NOT NULL |
| cost_usd | numeric(12,6) | NOT NULL — фактический из usage OpenRouter, фолбэк по прайсу конфига |
| latency_ms | int | NOT NULL |
| trace_id | text | NOT NULL — сквозной OTel trace |
| created_at | timestamptz | NOT NULL default now() |

### job_run — журнал плановых прогонов

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| job_name | text | NOT NULL |
| status | text | NOT NULL, CHECK ∈ (`running`,`success`,`partial`,`error`) |
| items_in / items_out | int | NOT NULL default 0 |
| error | text | NULL — заполнен при status=error ([F-I3]) |
| trace_id | text | NOT NULL |
| started_at | timestamptz | NOT NULL |
| finished_at | timestamptz | NULL |

## Отложено (по DOMAIN.md §4)

- `inbox_message` — этап 2, своя миграция.
- `linkedin_target` — этап 3, своя миграция.
- Полное `vacancy`, `application`, `interview_round`, `cover_letter` — этап 6.
