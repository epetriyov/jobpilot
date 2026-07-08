# Data Model: Этап 1 (миграция 0002_stage1)

Минимальный слой хранения НЕ расширяется новыми сущностями (DOMAIN.md §4); миграция дополняет `seen_vacancy` рабочими полями скоринга и снапшота. Одна миграция = один этап.

## Домен (без ORM)

| Объект | Слой | Поля / правила |
|---|---|---|
| `Score` | domain/relevance, VO frozen | `value: int 0..100`, `reason: str ≤200`, `prompt_version: str`, `model: str` — схема выхода LLM (R2) |
| `select_for_digest()` | domain/relevance | из скоренных: score ≥ threshold, сортировка убыв., максимум max_items (R4, [R-U3]) |
| `build_few_shot()` | domain/relevance | ≤10 последних Label → пары (user, assistant) с якорями 85/15 (R3, [R-U2]) |
| `VacancyScored` | событие | source_ref, score |
| `LabelAdded` | событие | source_ref, verdict |

## Миграция 0002_stage1 — ALTER seen_vacancy

| Колонка | Тип | Назначение |
|---|---|---|
| title | text NULL | снапшот для карточки/разметки |
| company | text NULL | — " — |
| url | text NULL | — " — |
| description_text | text NULL | очищенный текст (для labeled_vacancy и few-shot) |
| salary_from / salary_to | int NULL | рендер карточки |
| salary_currency | text NULL | — " — |
| score | int NULL | R1: NULL = не скорена |
| score_reason | text NULL | причина ≤200 |
| prompt_version | text NULL | R1: пересчёт при смене версии |
| score_model | text NULL | [R-C3]: фактическая модель |
| scored_at | timestamptz NULL | диагностика |

Индекс: `ix_seen_vacancy_scored (prompt_version, score)` — выборка «не скорено текущей версией» и «топ дайджеста».

## Правила репозитория (расширение SeenVacancyRepositoryPort)

- `unsent_scored(threshold, limit)` — скоренные, digest_sent_at IS NULL → кандидаты дайджеста.
- `unscored(prompt_version, limit)` — NULL score или иная prompt_version (R1).
- `save_score(ref, score: Score)` — идемпотентно.
- `snapshot(ref)` — снапшот полей для labeled_vacancy (разметка без похода в HH).
- Существующие `mark_seen`/`mark_digest_sent` — без изменений; mark_seen теперь пишет и снапшот-поля.

## Что НЕ делаем (границы)

- Таблицы `vacancy`, `application` — этап 6.
- `inbox_message` — этап 2 (секция negotiations этапа 1 не персистится).
- embedding labeled_vacancy — остаётся NULL до этапа 6.
