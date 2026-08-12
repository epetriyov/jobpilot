# Tasks: Скрейперы карьерных порталов (7 сайтов) — Этап 5

**Input**: Design documents from `/specs/005-sites/`

**Tests**: обязательны (constitution II): красный тест по кейсу TEST_CASES.md раздела «Сайты (C)»
— до кода. Домен SOURCING не трогаем (DOMAIN.md §5).

## Format: `[ID] [P?] [Story] Description`

Пометки: `[P]` — параллелизуемо; `⛔ЖЕЛЕЗО` — гейтится апгрейдом (INFRA.md §4.2), в рантайме
выключено до апгрейда, но golden/моки проходят в CI без браузера.

---

## Phase 1: Foundational — общий каркас адаптера + канарейка

- [x] T501 Конфиг: `SITES_ACTIVE`, `SITES_CANARY`, `SITES_HEAVY`, `SITES_RATE_LIMIT_SEC`,
  `SITES_USER_AGENT`, `SITES_EM_KEYWORDS`, `SITES_TIMEOUT_SEC` (contracts/env.md); валидация
  имён сайтов из фиксированного множества.
- [x] T502 [S-C10] Красные тесты → `adapters/sites/base.py` `SiteAdapter` + `http_transport.py`:
  между запросами ≥`SITES_RATE_LIMIT_SEC` (≥1 s), `User-Agent` из конфига, таймауты/ретраи
  (PLAN.md §7.3), проверка robots.txt целевого пути (запрет → сайт не запрашивается).
- [x] T503 [S-C9] Красные тесты → изоляция падений в `SiteAdapter`: пустой ответ/5xx/исключение
  → `SourceFetchFailed(source="site:<name>")` + инкремент `scraper_failures{site}` (S4);
  анти-бот/капча/логин-стена → `SourceFetchFailed(error="anti_bot")` + эскалация, **обход не
  реализуется** (S5, constitution IV); child-span на сайт (constitution V).
- [x] T504 [P] [S-C7]-домен: `em_filter.py` `filter_em(dtos, keywords)` (FR-004) — оставляет
  EM/лид-роли по ключам конфига; чистая функция, unit-тест на списке заголовков.
- [x] T505 [P] Golden-харнесс `tests/golden/sites/`: загрузка записанного payload, сверка с
  эталоном, diff-сигнал «скрейпер `<site>` сломан» ([S-C8]); контракт формы `VacancyDTO`
  (маппинг §data-model, [S-C7]).
- [x] T506 [F-I1] Миграция `0006_stage5`: `scraper_approval` + `ScraperApprovalPort`
  (`is_approved/approve/approved_sites`) + integration-тест (идемпотентность повторного
  `alembic upgrade`).
- [x] T507 [US3] Канарейка: в `application/run_daily_digest.py` вакансии сайта без одобрения
  (`SITES_CANARY` ∧ ¬`scraper_approval`) → секция «На проверку (canary)» с пометкой
  `site:<name> · canary`; одобренные → основной поток; бот `/approve_scraper <site>`
  (неизвестный сайт → отказ + список доступных); DRY_RUN-пометка «ТЕСТ» ([F-I2]).

## Phase 2: Волна A — лёгкие (SSR-HTML, httpx) — текущее железо 🎯 MVP

> По одной задаче на сайт: golden красный → чистый парсер → адаптер (httpx) → подключение к
> canary. Field completeness [S-C7]: title/url/company 100%, location ≥90%.

- [x] T510 [US1] [S-C7] **Яндекс** (yandex.ru/jobs): записать golden (SSR-HTML или JSON, если
  найден `yandex.ru/jobs/api/…`) → `parse_yandex` (красный [S-C8]) → `YandexAdapter(SiteAdapter)`
  → регистрация в `SITES_CANARY`. Salary «от X» → `(X,None)` (edge-case spec).
- [x] T511 [P] [US1] [S-C7] **VK** (team.vk.company/vacancy/): golden SSR-HTML → `parse_vk` →
  `VkAdapter` → canary.
- [x] T512 [P] [US1] [S-C7] **Avito** (career.avito.com/vacancies/): golden SSR-HTML → `parse_avito`
  → `AvitoAdapter` → canary. Внимание: career-сабдомен, НЕ avito.ru (research.md §2).

## Phase 3: Волна B — лёгкие-если-JSON (SPA + XHR-эндпоинт) — текущее железо при подтверждённом JSON

> Каждая задача начинается со **спайка [OQ-1]**: подтвердить публичный JSON-эндпоинт списка
> вакансий (XHR в devtools/прокси владельца). JSON подтверждён → лёгкий путь (httpx); эндпоинта
> нет → переклассифицировать сайт в Волну C (Playwright, ⛔ЖЕЛЕЗО), зафиксировать в research.md.

- [x] T520 [US1] [S-C7] **Сбер** (rabota.sber.ru): спайк JSON-эндпоинта `/search` [OQ-1] →
  golden (JSON) → `parse_sber` (красный [S-C8]) → `SberAdapter` (httpx) → canary. Нет JSON → C.
- [x] T521 [US1] [S-C7] **Т-Банк** (tbank.ru/career): спайк JSON-эндпоинта [OQ-1] → golden →
  `parse_tbank` → `TbankAdapter` (httpx) → canary. Нет JSON → C.
- [ ] T522 [US1] [S-C7] **Альфа** (job.alfabank.ru / digital.alfabank.ru): спайк JSON-эндпоинта +
  robots.txt [OQ-1]/[OQ-3] → golden → `parse_alfa` → `AlfaAdapter` (httpx) → canary. Нет JSON → C.

## Phase 4: Волна C — тяжёлые (Playwright) — ⛔ГЕЙТ АПГРЕЙДА ЖЕЛЕЗА (INFRA.md §4.2)

> Реализуются и тестируются на golden/моках сейчас; в рантайме выключены (`SITES_ACTIVE` их не
> содержит) до апгрейда на 4 vCPU / 8 GB. CI не запускает браузер.

- [ ] T530 ⛔ЖЕЛЕЗО `adapters/sites/browser_transport.py` `BrowserTransport` (Playwright, ленивый
  импорт, изоляция от рантайма лёгких сайтов) + тесты на моках без запуска Chromium.
- [ ] T531 ⛔ЖЕЛЕЗО [US1] [S-C7] **Ozon** (job.ozon.ru): спайк [OQ-2] — доступен ли список без
  капчи (только заголовки/куки)? golden → `parse_ozon` → `OzonAdapter` (BrowserTransport). Если
  защита требует **капчу** — сайт НЕ активируется, фиксируется «недоступен без нарушения ToS»
  (S5, constitution IV); `SourceFetchFailed(error="anti_bot")` при попытке в рантайме.
- [ ] T532 ⛔ЖЕЛЕЗО [P] Перенос провалившихся из Волны B (если Сбер/Т-Банк/Альфа оказались
  SPA-only) на `BrowserTransport` — те же `parse_<site>`/golden, смена транспорта (плюс к
  разделению транспорт↔парсер, plan.md).

## Phase 5: Eval и Polish

- [ ] T540 [S-E2] Датасеты `eval/datasets/sites_parse/<site>/v1.jsonl` (обезличенные ответы →
  эталонные поля) + раннер `eval/runners/sites_parse.py` (+ диспетчер в `run.py`): per-site
  field-completeness (title/url/company/location/salary); регресс completeness >5% против
  прошлого отчёта = блокер; отчёт `eval/reports/sites_parse_<date>.md`.
- [ ] T541 Гейты зелёные (ruff/mypy/import-linter/pytest; golden всех включённых сайтов; CI без
  сети/браузера); отчёт этапа (PLAN.md §7.6): сделано / acceptance / eval / что нужно для ручной
  проверки.
- [ ] T542 🖐 Владелец: по каждому включённому сайту 3-дневная канарейка (наблюдение секции «На
  проверку») → `/approve_scraper <site>`; закрытие этапа. Тяжёлые сайты — после апгрейда железа.

## Dependencies

T501 → T502–T505 (каркас) → T506–T507 (persist + canary) → Волна A (T510–T512) → Волна B
(T520–T522, каждая после своего спайка) → Волна C (T530–T532, после апгрейда железа) →
T540 (после ≥1 сайта) → T541 → T542. T510–T512 параллельны между собой; T520–T522 параллельны
после спайков.

## Соответствие кейсам TEST_CASES.md (раздел «Сайты (C)» + Eval)

| Кейс | Задача |
|---|---|
| [S-C7] маппинг/completeness | T505, T510–T512, T520–T522, T531 |
| [S-C8] golden-diff | T505, T510–T512, T520–T522, T531 |
| [S-C9] изоляция + `scraper_failures` | T503, T507 |
| [S-C10] rate-limit + UA + robots | T502 |
| [S-E2] `sites_parse` completeness | T540 |
| [F-I1] миграция | T506 |
| [F-I2] DRY_RUN | T507 |
| S5 анти-бот (не обходим) | T503, T531 |

## Гейт по железу (сводка)

| Волна | Задачи | Железо | Активация |
|---|---|---|---|
| A лёгкая | T510–T512 | текущее (1 vCPU/1 GB) | сразу |
| B лёгкая-если-JSON | T520–T522 | текущее (если JSON) | после спайка [OQ-1] |
| C тяжёлая | T530–T532 | 4 vCPU/8 GB (INFRA.md §4.2) | после апгрейда; капча → не активируем (S5) |
</content>
