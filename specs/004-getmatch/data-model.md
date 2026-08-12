# Data Model: Этап 4 (миграций НЕТ)

Домен Sourcing и минимальный слой хранения **не меняются** (DOMAIN.md §4, §5): GetMatch — новый адаптер за `VacancySourcePort`, пишет в существующий `seen_vacancy` (снапшот + скоринг этапа 1) как любой источник. Новых таблиц/enum/миграций нет.

## Домен (без изменений)

| Объект | Слой | Примечание |
|---|---|---|
| `Source` | domain/sourcing (StrEnum) | Значение `getmatch` уже в едином языке (DOMAIN §1). **Предложение**: убедиться, что `Source.GETMATCH = "getmatch"` присутствует в enum источников (если ещё не заведён на этапе 1) — это не изменение домена, а использование заявленного значения |
| `SourceRef` | VO | `SourceRef(source=Source.GETMATCH, site_name=None, external_id=str(offer["id"]))` — уникальность S1 |
| `Salary` | VO (frozen) | `from/to/currency` — все опциональны |
| `VacancyDTO` | контракт порта | Возврат `parse_getmatch_offers`; далее общий пайплайн ingest/дедуп/скоринг |

## Маппинг JSON offer → VacancyDTO (чистая функция `parse_getmatch_offers`)

| VacancyDTO поле | Источник в JSON | Правило |
|---|---|---|
| `source_ref` | `id` | `SourceRef(getmatch, None, str(id))`; дедуп по нему (S1) |
| `title` | `position` | обязателен; отсутствует → offer в raw (S-C6) |
| `company` | `company.name` | `null`/отсутствует (инкогнито) → `None` или «GetMatch (скрыто)»; offer не отбрасывается |
| `url` | `url` | абсолютизировать: `https://getmatch.ru` + `url`; отсутствует → raw (S-C6) |
| `salary` | `salary_hidden`, `salary_display_from/to`, `salary_currency` | `salary_hidden=true` → `Salary(None,None,None)`; иначе `Salary(from=salary_display_from, to=salary_display_to, currency=salary_currency)`; только `from` → `to=None` (S1) |
| `description_raw` | `offer_description` | HTML |
| `description_text` | `offer_description` | очистка HTML/эмодзи/переносов (S3, bs4); дополнить строкой стека из `skills_objects[].name` и локацией `location_items[].label` (полезно скорингу) |
| `raw` | весь offer | JSON целиком (S3: raw хранит оригинал); включает `salary_taxes`, `offer_type`, `published_at`, `is_active`, `skills_objects`, `location_items` |

**Фильтры/пропуски:**
- `is_active=false` → offer пропускается (закрытые не показываем).
- Нет `position` **или** нет `url` → VacancyDTO не создаётся, offer → raw-секция «непарсенное», warning-лог ([S-C6]).
- Дедуп внутри батча по `id` (повтор в выдаче не даёт второй DTO); межпрогонный дедуп — общий `seen_vacancy` (S1) и кросс-источниковый (company,title) 30 дней (S2) — на уровне пайплайна, не адаптера.

## Внешний контракт `/api/offers` (не доменная сущность)

```
GET https://getmatch.ru/api/offers?limit=<N>&offset=<M>
200 → {
  "meta":   {"total": int, "offset": int, "limit": int},
  "offers": [ { id, position, company{ id?, name, logotype? },
               url, salary_display_from, salary_display_to, salary_currency,
               salary_hidden, salary_taxes, offer_description,
               skills_objects[{name,slug,is_custom}],
               location_items[{label,format,exclude}],
               published_at, is_active, offer_type, type, ... } ]
}
```
Пагинация: `offset += limit` до `offset ≥ meta.total`. Структура зафиксирована golden'ом; изменение ловит golden-diff.

## Что НЕ делаем (границы)

- Никаких новых таблиц/миграций (в отличие от этапов 1/3/6).
- Не трогаем `Application`, `vacancy`, статусную машину — этап 6.
- Персональный фид `/api/vacancies` и его секреты — вне scope (research §5).
- Домен Sourcing/DOMAIN.md §3.1 не редактируется (только используем заявленное значение `getmatch`).
