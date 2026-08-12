# Quickstart: проверка этапа 5 руками

## Предусловия

В `.env` (contracts/env.md), старт с лёгкой волны на текущем железе:

```
SITES_ACTIVE=            # пусто в проде до одобрения; включаем по одному через canary
SITES_CANARY=yandex;vk;avito
SITES_RATE_LIMIT_SEC=1
SITES_USER_AGENT=JobPilot/1.0 (+owner-contact)
SITES_EM_KEYWORDS=engineering manager;руководитель разработки;head of engineering;team lead;тимлид
```

Тяжёлые (Playwright) сайты — `ozon` и любые провалившиеся из Волны B — НЕ включать до апгрейда
железа (4 vCPU / 8 GB, INFRA.md §4.2).

## 1. Гейты, миграция, моки

```bash
make lint && make test          # golden всех включённых сайтов + изоляция падений + rate-limit
make migrate                    # 0006_stage5: scraper_approval
```

`make test` НЕ ходит в сеть и НЕ запускает браузер — golden на записанных ответах ([S-C7]/[S-C8]),
изоляция падений и `scraper_failures{site}` ([S-C9]), rate-limit/UA ([S-C10]).

## 2. Канарейка: один сайт за раз

```bash
docker compose up -d
```

Дневной дайджест (10:00 МСК) → вакансии сайтов из `SITES_CANARY` приходят в секцию
**«На проверку (canary)»** с пометкой `site:<name> · canary`. Проверьте на 2–3 карточках:
ссылка открывает реальную вакансию портала; company = имя компании; title/локация заполнены;
вилка (если есть) корректна.

## 3. Одобрение

Наблюдайте канарейку 3 дня. Убедившись в качестве:

```
/approve_scraper yandex
```

Следующий дайджест несёт вакансии `yandex` в **основном потоке** (не в canary). Повторный
`/approve_scraper yandex` идемпотентен; `/approve_scraper unknown` → отказ со списком сайтов.

## 4. Изоляция падений

Сломать один сайт (например, временно указать неверный путь) → job завершается `partial`:
вакансии остальных сайтов и HH/GetMatch собраны, `scraper_failures{site}` инкрементнут (виден в
Grafana), алерт по порогу (этап 0). Никаких обходов капчи: анти-бот → `SourceFetchFailed(error="anti_bot")`.

## 5. Волна B (лёгкие-если-JSON) — после спайка

Для Сбер/Т-Банк/Альфа сначала подтвердите JSON-эндпоинт (devtools/прокси владельца, [OQ-1]).
JSON есть → добавьте сайт в `SITES_CANARY`, повторите шаги 2–3. Нет JSON → сайт уходит в тяжёлую
волну (см. §6).

## 6. Волна C (тяжёлые, Playwright) — ТОЛЬКО после апгрейда железа

После перехода на 4 vCPU / 8 GB (INFRA.md §4.2):

```bash
make install-playwright         # ставит Chromium
```

Добавьте `ozon` (и провалившиеся из Волны B) в `SITES_CANARY`, повторите шаги 2–3. Если портал
требует капчу — сайт не активируется (S5): это ожидаемый исход, не баг.

## 7. Eval

```bash
make eval CONTEXT=sites_parse   # per-site field-completeness; регресс >5% = блокер ([S-E2])
```

## 8. 🖐 Закрытие этапа

По каждому включённому сайту: 3-дневная канарейка → визуальная проверка карточек →
`/approve_scraper <site>`. Golden зелёные, `sites_parse` без регресса. Тяжёлые сайты — после
апгрейда железа.
</content>
