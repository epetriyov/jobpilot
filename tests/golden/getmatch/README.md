# Golden GetMatch (`/api/offers`)

Обезличенный сокращённый снимок публичного JSON-эндпоинта
`GET https://getmatch.ru/api/offers` — фикстура для golden-diff теста чистого
парсера `parse_getmatch_offers` ([S-C5], [S-C0b]-аналог) и деградации в raw
([S-C6]).

## Файлы

- `offers.json` — валидный ответ `/api/offers` (6 offers), покрывает ветки маппинга:
  - открытая вилка `salary_hidden=false` (from+to, только from);
  - `salary_hidden=true` → `Salary(None,None,None)`;
  - `company.name=null` (инкогнито-публикация) → плейсхолдер `GetMatch (скрыто)`
    (домен требует `company: str`, поэтому не `None`);
  - `is_active=false` → offer пропускается (нет в expected);
  - несколько `location_items` → склейка меток.
- `offers.expected.json` — эталонная контрактная форма (5 активных offers; закрытый
  `40004` отсутствует). Сверяется `harness.assert_golden`.
- `offers_unknown_format.json` — offers без `position`/`url` и «чужой» схемы:
  VacancyDTO не создаётся, offer уходит в raw-секцию «непарсенное» ([S-C6]).

## Происхождение данных

Значения (компании, тексты, id) **синтетические/обезличенные**: реальные данные
владельца и публичные офферы не воспроизводятся дословно. Структура полей и их
типы соответствуют исследованию (`specs/004-getmatch/research.md §3`,
`data-model.md`). Живой сетевой запрос к `getmatch.ru` в этом окружении не
выполнялся: источник **off-by-default** и `robots.txt` содержит `Disallow: /api/`
— обезличенный golden достаточен для CI без сети (fake-режим).

## Регрессия

Изменение структуры ответа `/api/offers` (переименование/удаление полей) ломает
golden-diff тест `tests/unit/test_parse_getmatch.py::test_parse_getmatch_golden`
с сигналом «парсер GetMatch сломан» → парсер чинится под новую структуру, golden
пере-записывается обезличенным снимком.
