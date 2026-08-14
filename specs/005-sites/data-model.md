# Data Model: Этап 5 (миграция 0006_stage5)

> Домен SOURCING НЕ меняется (DOMAIN.md §5). Ниже — маппинг карточки портала в существующий
> `Vacancy` и единственная новая персист-сущность: факт одобрения сайта (`/approve_scraper`).

## Маппинг карточки сайта → доменный `Vacancy` (переиспользование §3.1)

| Домен (существует) | Источник — поле карточки портала | Правило |
|---|---|---|
| `Source` | — | всегда `Source.SITE` |
| `SourceRef.site_name` | — | имя адаптера ∈ {yandex, vk, avito, tbank, ozon, alfa, sber, navio, mts, rwb} |
| `SourceRef.external_id` | id/slug вакансии на портале | стабильный ключ карточки; при отсутствии — хеш(url) |
| `Vacancy.title` | заголовок вакансии | обязательно (completeness 100%, [S-C7]) |
| `Vacancy.company` | — | = имя компании адаптера (портал = один работодатель); 100% |
| `Vacancy.url` | ссылка на карточку | абсолютный URL, очищен от utm/трекинга; 100% |
| `Vacancy.location` | город/формат (office/remote) | ≥90% ([S-C7]); отсутствует → None |
| `Vacancy.description_text` | описание (если в списке есть) | HTML вычищен (S3); часто пусто в списке — подтягивается при необходимости |
| `Vacancy.raw` | сырой payload карточки (JSON/HTML-фрагмент) | оригинал (S3) |
| `Salary(from?, to?, currency?)` | вилка портала (если публикуется) | «от X» → `(X, None, cur)`; нет → `(None,None,None)`; текст-мусор НЕ течёт в company/title |

Ничего не добавляется в агрегат `Vacancy`: этап 5 — новые адаптеры, не новые поля (DOMAIN.md §5).

## Контракт адаптера (app/adapters/sites)

| Объект | Тип | Поля / правила |
|---|---|---|
| `SiteAdapter(VacancySourcePort)` | базовый класс | `site_name`, `transport`, `parse_fn`, `keywords`; `fetch()` → transport → `parse_<site>` → `filter_em` → `list[VacancyDTO]`; изоляция падений → `SourceFetchFailed(source="site:<name>")` + `scraper_failures{site}` (S4, [S-C9]); rate-limit ≥1 s, UA из конфига ([S-C10]) |
| `parse_<site>(payload)` | чистая функция | `payload -> list[VacancyDTO]`, без I/O; golden ([S-C7]/[S-C8]) |
| `filter_em(dtos, keywords)` | функция | оставляет EM/лид-роли по ключам конфига (FR-004) |
| `Transport` | протокол | `HttpTransport` (httpx JSON/HTML + robots-check) \| `BrowserTransport` (Playwright, ленивый импорт, тяжёлая волна) |
| анти-бот | ошибка | капча/стена/логин → `SourceFetchFailed(error="anti_bot")` + эскалация; НЕ обходится (S5) |

## Таблица scraper_approval (0006_stage5)

Персист факта `/approve_scraper <site>` (минимальный слой хранения — DOMAIN.md §4; это НЕ
доменный агрегат, а служебный флаг источника).

| Колонка | Тип | Ограничения |
|---|---|---|
| site_name | text | PK, ∈ {yandex, vk, avito, tbank, ozon, alfa, sber, navio, mts, rwb} (CHECK `ck_scraper_approval_site`; расширен с 7 до 10 миграцией 0011_wave_b_sites) |
| approved_at | timestamptz | NOT NULL default now() — момент одобрения владельцем |
| approved_by_chat_id | bigint | NOT NULL — OWNER_CHAT_ID (аудит) |

Правило canary (FR-007): сайт из `SITES_CANARY` без строки в `scraper_approval` → вакансии в
секцию «На проверку (canary)»; строка есть → основной поток. `seen_vacancy` не расширяется —
`source_ref` уже несёт `site_name`; `canary`-пометка карточки вычисляется из `scraper_approval`
на момент сборки дайджеста (не хранится в вакансии на этапах 0–5).

## Порт (существующий, без изменений)

`VacancySourcePort.fetch() -> list[VacancyDTO]` — тот же контракт, что у HH-email и GetMatch.
Новый служебный порт `ScraperApprovalPort`: `is_approved(site) -> bool`, `approve(site, chat_id)`,
`approved_sites() -> set[str]`.

Время в БД — UTC. Миграция — Alembic, одна на этап (`0006_stage5`).
</content>
