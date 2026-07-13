# Contract: адаптер HH (adapters/hh)

Все вызовы HH — только внутри `adapters/hh/`; наружу — домен (Vacancy) и узкие порты.

## Порты

- `VacancySourcePort` (существующий): `HhVacancySource.fetch() -> list[Vacancy]` — поиск по запросам конфига + similar от откликов/избранного, полный текст дозапрашивается только для невиденных.
- `PublisherPort` (существующий): `HhResumePublisher.publish()` — поднятие резюме; результат: published | skipped_limit (не исключение! [S-C3]).
- `HhNegotiationsPort` (новый, узкий): `fetch_updates(since) -> list[NegotiationUpdate(employer, vacancy_title, text, url, updated_at)]`.

## Аутентификация ([S-C2])

- Заголовки: `Authorization: Bearer <access>`, `HH-User-Agent: <из конфига>`.
- access token живёт в памяти; получен из refresh token при старте/по требованию.
- Ровно один сценарий повтора: запрос → 401 → refresh → тот же запрос один раз → 401 снова = ошибка наружу (SourceFetchFailed).
- Значения токенов не логируются (санитайзер + тест).

## Обработка ответов

| Ситуация | Поведение |
|---|---|
| 200 search | маппинг в Vacancy по golden ([S-C1]); вилка «от X» → Salary(from=X, to=None) |
| 401 | refresh + повтор 1 раз ([S-C2]) |
| 429 / touch_limit на publish | штатный skip: лог info, метрика publish_skipped, job success ([S-C3]) |
| 403/5xx/сеть | SourceFetchFailed(source="hh"), job partial/error (S4) |
| пустая выдача | нормальный результат, «новых нет» |

## Golden-файлы (tests/golden/hh/)

- `search_page.json` — реальная страница /vacancies (обезличенная), включая вакансию с вилкой «от X» без «до».
- `vacancy_full.json` — полная вакансия /vacancies/{id} с HTML в description.
- `similar.json` — ответ similar_vacancies.
- `publish_429.json` — тело ответа лимита поднятия.
- `negotiations.json` — страница переписки с непрочитанным сообщением.
- `token_refresh.json` — ответ обмена refresh token.

Обновление golden — только осознанным коммитом (AGENT_GUIDE §3).

## Лимиты и этика

- Последовательные запросы, пауза из конфига (по умолчанию 0.5с), никакого параллельного обстрела.
- Пагинация ограничена конфигом (2 страницы × 50 на запрос).
