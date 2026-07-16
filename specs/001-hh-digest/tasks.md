# Tasks: Вся работа с HH — выгрузка в чат (Этап 1)

**Input**: Design documents from `/specs/001-hh-digest/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: обязательны (constitution II): каждая задача реализации начинается с падающего теста по кейсу TEST_CASES.md (ссылки в `[…]`). Golden-файлы пишутся ДО адаптера.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Foundational (Blocking Prerequisites)

- [x] T101 Конфиг этапа 1: `HH_*`, `HH_SEARCH_QUERIES`, `DIGEST_CRON`, `PUBLISH_INTERVAL_HOURS`, `FEWSHOT_*` в `app/config.py` (contracts/env.md); секреты HH → `secret_values()`; красный тест: значения HH-токенов маскируются в логах ([X-U1] расширение)
- [x] T102 [F-I1] Миграция `0002_stage1` (data-model.md: снапшот+скор в seen_vacancy, индекс) + красный integration-тест: upgrade head идемпотентен, новые колонки на месте
- [x] T103 [P] Домен relevance (красные тесты [R-U2] [R-U3] → реализация): `app/domain/relevance/` — Score VO (0..100, reason≤200), `select_for_digest` (порог/топ-50/убывание), `build_few_shot` (≤10 последних, якоря 85/15)

## Phase 2: User Story 1 — Дайджест (P1) 🎯 MVP

> Пересмотр 2026-07-15: API HH недоступен. T104–T107, T115, T117 переопределены под userbot HH-бота (Telethon) + web-скрейпер рекомендаций (Playwright) + web-publish. Мёртвый API-код (hh/auth.py, cli/oauth_hh.py, test_hh_auth.py) удалён.

- [x] T104 [US1] [S-C4] Golden `tests/golden/hh_telegram/*.txt` (≥20 реальных сообщений HH-бота, обезличенные) → красный parse-тест → `adapters/hh/telegram_source.py` (парс title/company/url; непарсенное → raw-секция, warning) + `adapters/telegram_userbot/` (Telethon-обёртка чтения диалога) + CLI `app/cli/login_userbot.py`
- [x] T105 [US1] [S-C1] Golden `tests/golden/hh_web/*.html` (страница рекомендаций) → красный маппинг-тест → `adapters/hh/web_source.py` (Playwright по сохранённому профилю; Vacancy: вилка «от X» без «до», S3-очистка) + CLI `app/cli/hh_login.py` (ручной вход в браузер-профиль)
- [x] T106 [US1] [S-C2] Красный тест на модифицированном golden HTML → diff-сигнал «скрейпер сломан»; [S-C4b] логин/капча → SourceFetchFailed(hh_web) + эскалация, без обхода (S5); [S-C10] пауза ≥1с, честный User-Agent
- [x] T107 [US1] Свести источники по `HH_SOURCES` в композиции: список активных `VacancySourcePort` (telegram/web/fake); падение одного не роняет остальные (S4)
- [x] T108 [US1] [R-U1] [R-U5] Красные тесты → `application/score_vacancy.py`: скорит только unscored(prompt_version) (R1); невалидный выход → 1 retry → skip warning (R2); few-shot из labeled (R3); llm_call пишется (O1 — фейк)
- [x] T109 [US1] [R-U4] [R-C1] Красный тест промпт-сборки: текст вакансии в data-блоке, не в system (R5); ни одна строка секретов из env не попадает в промпт
- [x] T110 [US1] Красный integration-тест → `application/run_daily_digest.py`: сбор → mark_seen(снапшот) → скоринг новых → select_for_digest → карточки → mark_digest_sent; DRY_RUN помечает «ТЕСТ» ([F-I2]); частичный сбой источника → partial (S4)
- [x] T111 [US1] Бот: рендер карточки (title/company/вилка/score+reason, кнопки 👍/👎/🔗), команда `/digest`; worker: cron 10:00 МСК через run_job; [X-I1] e2e-тест дайджест-флоу на HH-фикстурах со спанами шагов

## Phase 3: User Story 2 — Разметка и /train (P1)

- [x] T112 [US2] Красный тест → use case `LabelVacancy`: колбэк 👍/👎 → upsert labeled_vacancy по source_ref из снапшота seen (повторное нажатие обновляет вердикт, не дублирует); событие LabelAdded; строка в `eval/datasets/relevance/v1.jsonl` (append-only)
- [x] T113 [US2] Бот: обработчик callback_query (`label:<verdict>:hh:<id>`), подтверждение answerCallbackQuery, обновление клавиатуры; `/train` — счётчики размеченного и остаток до 30
- [x] T114 [P] [US2] [R-C3] Contract-тест: смена `LLM_MODEL_SCORING` в конфиге меняет модель в llm_call без правок кода (на записанных ответах)

## Phase 4: User Story 3 — Publish каждые 4 часа (P2)

- [ ] T115 [US3] [S-C3] Красный тест (Playwright на сохранённом HTML): «поднять» → published; лимит «ещё рано» → skip без ретрая, publish_skipped, job success; DRY_RUN → клик не выполняется → `adapters/hh/web_publish.py` (PublisherPort)
- [~] T116 (use case+worker+/publish готовы; web-адаптер ждёт golden) [US3] `application/publish_resume.py` + worker-слот 4ч + `/publish`; метрика publish_skipped в `obs/metrics.py`

## Phase 5: User Story 4 — Непарсенные сообщения HH-бота (P2)

- [ ] T117 [US4] Красный тест: сообщение HH-бота нового формата → raw-секция дайджеста, warning ([S-C4]/S-C6-механика) — переписка HH теперь приходит тем же userbot-каналом, отдельного negotiations-API нет

## Phase 6: User Story 5 — Доступ к источникам (P3)

- [x] T118 [US5] CLI-хелперы доступа (заменяют oauth_hh, API нет): `login_userbot.py` (Telethon: api_id/api_hash + код → session-файл) и `hh_login.py` (Playwright headful: ручной вход в браузер-профиль HH, сессия в volume). Токены/куки не логируются; хелперы запускает владелец один раз

## Phase 7: Eval и Polish

- [ ] T119 [R-E1] Раннер `relevance` в `eval/runners/run.py`: precision/recall/F1 c порогами 0.7 как assertions; режим записанных ответов для CI; поддержка `MODEL_B=` для сравнения (отчёт с ΔF1, вердикт по |ΔF1| ≤ 0.05)
- [ ] T120 Обновить дашборд-заметки/квикстарт при необходимости; `make lint`+`make test` зелёные; финальный отчёт (DoD §7)
- [ ] T121 🖐 Ручная фаза владельца: 3 дня DRY_RUN, разметка ≥30, `make eval CONTEXT=relevance` + сравнение Flash-Lite vs Flash, явное включение DRY_RUN=false

## Dependencies & Execution Order

- Phase 1 блокирует всё; T104 (golden) блокирует T105–T107; T108–T109 зависят от T103; T110 — от T105–T108; T111 — от T110.
- US2 (T112–T113) зависит от снапшота (T102) и карточек (T111); T114 независим [P].
- US3/US4/US5 независимы друг от друга после Phase 1; могут идти параллельно с US2.
- T119 требует датасета (T112) — реальный прогон после разметки ≥30 (T121).

## Соответствие кейсам TEST_CASES.md

| Кейс | Задача |
|---|---|
| [S-C1] | T105 |
| [S-C2] | T106 |
| [S-C3] | T115 |
| [S-C4] | T107 |
| [R-U1] | T108 |
| [R-U2] | T103 |
| [R-U3] | T103 |
| [R-U4] | T109 |
| [R-U5] | T108 |
| [R-C1] | T109 |
| [R-C2] | покрыт этапом 0 (suite общий) |
| [R-C3] | T114 |
| [R-E1] | T119, T121 |
| [X-I1] | T111 |
| [X-U1] | T101 |
| [F-I2] | T110, T116 |
