# Data Model: Этап 3 (миграция 0004_stage3)

## Домен (app/domain/networking, без ORM)

| Объект | Тип | Поля / правила |
|---|---|---|
| `InviteStatus` | StrEnum | proposed → sent → accepted (только вперёд, N3) |
| `InviteDraft` | агрегат | title (роль), company, search_url, invite_text (≤300, N2), status; `transition(to)` → `IllegalTransition` при недопустимом переходе ([N-U1]) |
| `InviteText` | схема LLM | text: str ≤300 (реджект → 1 retry → шаблонный фолбэк) |
| `build_pairs()` | функция | декартово произведение companies×roles минус существующие не-accepted пары ([N-C1]) |
| `people_search_url()` | функция | percent-encoding роли+компании (включая кириллицу) |
| `IllegalTransition` | ошибка | единое имя с CRM (§3.3) — доменная ошибка переходов |

## Таблица linkedin_target (0004_stage3)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| title | text | NOT NULL — роль адресата |
| company | text | NOT NULL |
| search_url | text | NOT NULL |
| invite_text | text | NOT NULL, длина ≤300 (CHECK) |
| status | text | NOT NULL CHECK ∈ (proposed, sent, accepted) |
| created_at | timestamptz | NOT NULL default now() |
| sent_at / accepted_at | timestamptz | NULL — заполняются переходами |

Частичный уникальный индекс: `uq_linkedin_target_active (company, title) WHERE status <> 'accepted'` — дедуп еженедельных запусков (research §3).

ПД адресатов (имена, профили) не хранятся по построению (N1, минимизация ПД).

## Порт

`InviteRepositoryPort`: `active_pairs() -> set[(company,title)]`, `add(draft) -> id`, `get(id)`, `set_status(id, status, at)`, `pending_older_than(days) -> list`, `counts() -> dict[status,int]`.
