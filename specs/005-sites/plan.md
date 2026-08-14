# Implementation Plan: Скрейперы карьерных порталов (10 сайтов) — Этап 5

**Branch**: `005-sites` | **Date**: 2026-08-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-sites/spec.md`

## Summary

Семь адаптеров `VacancySourcePort` (Яндекс, VK, Avito, Т-Банк, Ozon, Альфа, Сбер) поверх
существующего контекста SOURCING — **домен не меняется** (DOMAIN.md §5). Общий базовый класс
`SiteAdapter` даёт кросс-сайтовую механику (rate-limit ≥1 s, честный UA, robots.txt, изоляция
падений → `SourceFetchFailed` + `scraper_failures{site}`, child-span), а сайт-специфичное ядро
— чистая функция `parse_<site>(payload) -> list[VacancyDTO]` под golden-тестом ([S-C7]/[S-C8]).
Приоритет доступа: **JSON/SSR-HTML через httpx** (лёгкие, текущее железо) → **Playwright**
только для SPA без JSON (тяжёлые, гейт апгрейдом железа, INFRA.md §4.2). EM-фильтр — адаптерный
(FR-004). Канарейка + `/approve_scraper <site>` — человек в контуре (constitution VI). Eval
`sites_parse` per-site — field-completeness ([S-E2]).

**Реализация разбита на волны** (см. research.md §2, tasks.md):
- **Волна A** (httpx SSR-HTML, текущее железо): Яндекс, VK, Avito.
- **Волна B** (httpx JSON после XHR-спайка, текущее железо): Сбер, Т-Банк, Альфа.
- **Волна C** (Playwright, гейт апгрейдом до 4 vCPU / 8 GB): Ozon + любой из Сбер/Т-Банк/Альфа,
  оказавшийся SPA-only.
- **Волна D** (httpx публичные JSON-фиды single-employer, текущее железо): Navio, МТС, RWB/WB —
  добавлена после исходного плана (7→10 сайтов), синхронизирована ретроспективно (docs/decisions/ADR-001).
  `mws` рассмотрен и исключён (Qrator рвёт прод-egress, scraping-risks.md §3a).

## Technical Context

**Language/Version**: Python 3.12 (без изменений)

**Dependencies**: `httpx` (есть), HTML-парсер `selectolax`/`lxml` (лёгкая волна); `playwright`
— ТОЛЬКО для тяжёлой волны, ставится опционально и не тянется в рантайм лёгких сайтов

**Storage**: минимальный слой (DOMAIN.md §4); новое — персист факта `/approve_scraper` (см.
data-model.md), таблица `seen_vacancy` переиспользуется как есть (`source_ref` уже поддерживает
`site_name`)

**Testing**: golden (contract) per-site + unit чистых парсеров + integration изоляции падений;
eval `sites_parse`. CI гоняет golden/unit без сети (записанные ответы)

**Platform**: текущий прод 1 vCPU / ~1 GB / swap 0 — тянет ТОЛЬКО лёгкую волну; тяжёлая — после
апгрейда (INFRA.md §4.2)

**Constraints**: ноль обхода капчи/анти-бота (S5, constitution IV); robots.txt уважается;
≤1 rps; секретов нет

**Scale/Scope**: 7 сайтов, дневной сбор в общем пайплайне; дайджест ≤50 карточек (R4) — фильтр
по score, а не по источнику

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Слои | Домен SOURCING без изменений; парсеры/адаптеры — `adapters/sites/`, реализуют `VacancySourcePort`; EM-фильтр адаптерный; бот тонкий (`/approve_scraper`) | PASS |
| II. Test-first | [S-C7] (маппинг), [S-C8] (golden-diff), [S-C9] (изоляция+`scraper_failures`), [S-C10] (rate-limit+UA), [S-E2] (completeness) — красные до кода | PASS |
| III. LLM | LLM не добавляется: скоринг вакансий сайтов идёт существующим `LlmPort` (этап 1); адаптеры LLM не вызывают | PASS (N/A) |
| IV. Безопасность | S5: анти-бот/капча → `SourceFetchFailed(error="anti_bot")` + эскалация, обход не проектируется; robots.txt; секретов нет; тексты вакансий — недоверенные данные (S5) | PASS |
| V. Наблюдаемость | `scraper_failures{site}`, child-span на сайт, счётчики in/filtered в `job_run` | PASS |
| VI. Человек в контуре | Канарейка «На проверку» + `/approve_scraper <site>` до вливания в основной поток; DRY_RUN | PASS |

**Gate по железу (не constitution, но блокер активации):** тяжёлые (Playwright) адаптеры не
включаются в `SITES_ACTIVE` до апгрейда железа (INFRA.md §4.2). Golden/моки этих адаптеров
проходят в CI без браузера.

## Project Structure

```text
app/
├── domain/sourcing/            # БЕЗ ИЗМЕНЕНИЙ (Vacancy, SourceRef, Salary, Source.SITE — уже есть)
├── ports/sourcing.py           # VacancySourcePort — БЕЗ ИЗМЕНЕНИЙ
├── adapters/sites/
│   ├── base.py                 # NEW: SiteAdapter(VacancySourcePort): rate-limit, UA, robots,
│   │                           #      таймауты/ретраи, изоляция → SourceFetchFailed + scraper_failures, span
│   ├── em_filter.py            # NEW: filter_em(dtos, keywords) (FR-004)
│   ├── http_transport.py       # NEW: httpx-транспорт (JSON/HTML), robots-check
│   ├── browser_transport.py    # NEW (тяжёлая волна): Playwright-транспорт; импортится лениво
│   ├── yandex.py  parse_yandex()      # лёгкий
│   ├── vk.py      parse_vk()          # лёгкий
│   ├── avito.py   parse_avito()       # лёгкий
│   ├── sber.py    parse_sber()        # лёгкий-если-JSON (спайк)
│   ├── tbank.py   parse_tbank()       # лёгкий-если-JSON (спайк)
│   ├── alfa.py    parse_alfa()        # лёгкий-если-JSON (спайк)
│   └── ozon.py    parse_ozon()        # тяжёлый (Playwright), гейт апгрейдом
├── adapters/persistence/       # +scraper_approval (persist /approve_scraper), миграция 0006_stage5
├── application/
│   └── run_daily_digest.py     # +подключение активных сайт-адаптеров; canary-секция «На проверку»
├── bot/                        # +/approve_scraper <site> (+ подсказка списка сайтов)
└── worker/                     # активные сайты в дневном сборе (существующий job)

tests/
├── unit/adapters/sites/test_parse_<site>.py   # чистые парсеры (S-C7 маппинг)
├── golden/sites/<site>/…                       # записанные ответы + эталон (S-C8 diff)
├── contract/test_site_adapter.py               # base: rate-limit, UA, изоляция падений (S-C9, S-C10)
└── integration/test_sites_isolation.py         # падение одного сайта → partial, остальные собраны

eval/datasets/sites_parse/<site>/v1.jsonl        # completeness (S-E2)
eval/runners/sites_parse.py                       # per-site completeness + регресс-гейт >5%
```

**Structure Decision**: зеркало этапов 1/4 (адаптеры источников + golden + canary). Ключевое —
разделение **транспорт (httpx|playwright) ↔ чистый парсер**: golden тестирует парсер на
записанном payload и не зависит от способа добычи; смена HTML→JSON или httpx→Playwright не ломает
golden и не трогает домен (DOMAIN.md §5 «смена API→scrape→email — только новые адаптеры»).

**Robots-парсер: `protego` вместо stdlib `urllib.robotparser`.** `http_transport.py` проверяет
robots.txt целевого пути (FR-006, [S-C10]) через `protego.Protego` (парсер из Scrapy), а не
`urllib.robotparser.RobotFileParser`. Причина: `urllib` ошибочно нормализует `Disallow: /?` →
`/` (блокирует весь сайт вместо трекинг-параметров) и неверно трактует `*`-wildcard / `$`-якорь;
на реальном robots Яндекса это давало ложный запрет и блокировало 🟢-источник. `protego` трактует
эти паттерны корректно. ⚠️ У `protego` обратный urllib порядок аргументов:
`can_fetch(url, user_agent)`. Решение зафиксировано в docs/decisions/ADR-001.

## Волны реализации (привязка к железу)

| Волна | Сайты | Транспорт | Железо | Гейт |
|---|---|---|---|---|
| **A. Лёгкая (подтв.)** | Яндекс, VK, Avito | httpx (SSR-HTML) | текущее | нет — едет сразу |
| **B. Лёгкая-если-JSON** | Сбер, Т-Банк, Альфа | httpx (JSON) после спайка | текущее (если JSON) | XHR-спайк [OQ-1]; при SPA-only → волна C |
| **C. Тяжёлая** | Ozon (+ провалившиеся из B) | Playwright | 4 vCPU / 8 GB (INFRA.md §4.2) | апгрейд железа; анти-бот с капчей → S5, не активируем |

Волна A даёт всю ценность на текущем железе. Волна B — по мере закрытия [OQ-1], без ожидания
апгрейда, если JSON подтверждён. Волна C — готова «одной строкой конфига» после апгрейда.

## Сверка с DOMAIN.md / AGENT_GUIDE.md / TEST_CASES.md

- §3.1 SOURCING: `VacancySourcePort.fetch() -> list[VacancyDTO]`, `SourceRef(source, site_name?,
  external_id)`, `Salary(from?, to?, currency?)` — переиспользуются дословно; новизна — значение
  `Source.SITE` + `site_name`. Инварианты S1–S5 → тесты [S-C7]–[S-C10]; S5-анти-бот → `error="anti_bot"`.
- §1 «Канарейка», «Дайджест»: секция «На проверку (canary)» + `/approve_scraper` — термины дословно.
- §5 «Как расширять домен»: новый источник = новый адаптер + golden + canary, домен Sourcing не
  меняется — этап 5 полностью в этой рамке.
- TEST_CASES.md раздел «Сайты (C)»: [S-C7], [S-C8], [S-C9], [S-C10]; Eval [S-E2] `sites_parse`.
- Чек-лист «Новый источник» (AGENT_GUIDE): термин есть → кейсы есть → адаптер + golden → canary →
  eval-completeness → owner `/approve_scraper`.
</content>
