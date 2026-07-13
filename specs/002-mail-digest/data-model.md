# Data Model: Этап 2 (миграция 0003_stage2)

## Домен (app/domain/correspondence, без ORM)

| Объект | Тип | Поля / правила |
|---|---|---|
| `InboxMessage` | VO frozen | source ∈ {gmail, linkedin_gmail, hh}, sender, subject, summary (≤2 строк), url, received_at, section ∈ {mail, linkedin, hidden} |
| `MailVerdict` | схема LLM | is_job: bool, summary: str ≤200, невалидно → retry → unclassified-фолбэк (M2) |
| `prefilter()` | функция | эвристика M1: whitelist-домены → кандидат; blacklist-рассылки → отсев до LLM; linkedin.com + шаблон темы → секция linkedin без LLM; hh.ru-уведомления → hidden (покрыто negotiations) |

## Таблица inbox_message (0003_stage2)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | bigserial | PK |
| gmail_id | text | UNIQUE NOT NULL — дедуп повторной обработки |
| source | text | NOT NULL CHECK ∈ (gmail, linkedin_gmail, hh) |
| sender | text | NOT NULL |
| subject | text | NOT NULL |
| summary | text | NULL — summary LLM или NULL для unclassified |
| url | text | NOT NULL |
| section | text | NOT NULL CHECK ∈ (mail, linkedin, hidden) |
| received_at | timestamptz | NOT NULL |
| processed_at | timestamptz | NOT NULL default now() |

Тело письма не хранится нигде (M4-производная). Индекс по received_at (выборка «за 24ч»).

## Порты

- `InboxPort.fetch_since(dt) -> list[RawEmail]` (RawEmail: gmail_id, sender, subject, snippet, body_text, received_at, url) — body_text живёт только в памяти процесса до промпта.
- `InboxMessageRepositoryPort`: `is_processed(gmail_id)`, `add(InboxMessage)`, `recent_sections(since) -> dict[section, list[InboxMessage]]`.
