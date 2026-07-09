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

- [ ] T104 [US1] Golden-файлы `tests/golden/hh/`: search_page.json (с вилкой «от X» без «до»), vacancy_full.json (HTML), similar.json, token_refresh.json — записываются владельцем/вручную из реальных ответов, обезличенные
- [ ] T105 [US1] [S-C1] Красный contract-тест маппинга → `adapters/hh/mapping.py`: JSON HH → Vacancy (Salary(from=X, to=None); description_raw → S3-очистка доменом)
- [ ] T106 [US1] [S-C2] Красный contract-тест (respx): 401 → refresh → повтор ровно 1 раз; повторный 401 → SourceFetchFailed → `adapters/hh/auth.py` + `client.py` (HH-User-Agent, пауза между запросами [S-C10]-механика)
- [ ] T107 [US1] [S-C4] Красный contract-тест: отклики → similar → влиты с дедупом → `adapters/hh/source.py` (VacancySourcePort: запросы конфига + similar; полный текст только для невиденных)
- [x] T108 [US1] [R-U1] [R-U5] Красные тесты → `application/score_vacancy.py`: скорит только unscored(prompt_version) (R1); невалидный выход → 1 retry → skip warning (R2); few-shot из labeled (R3); llm_call пишется (O1 — фейк)
- [x] T109 [US1] [R-U4] [R-C1] Красный тест промпт-сборки: текст вакансии в data-блоке, не в system (R5); ни одна строка секретов из env не попадает в промпт
- [ ] T110 [US1] Красный integration-тест → `application/run_daily_digest.py`: сбор → mark_seen(снапшот) → скоринг новых → select_for_digest → карточки → mark_digest_sent; DRY_RUN помечает «ТЕСТ» ([F-I2]); частичный сбой источника → partial (S4)
- [ ] T111 [US1] Бот: рендер карточки (title/company/вилка/score+reason, кнопки 👍/👎/🔗), команда `/digest`; worker: cron 10:00 МСК через run_job; [X-I1] e2e-тест дайджест-флоу на HH-фикстурах со спанами шагов

## Phase 3: User Story 2 — Разметка и /train (P1)

- [ ] T112 [US2] Красный тест → use case `LabelVacancy`: колбэк 👍/👎 → upsert labeled_vacancy по source_ref из снапшота seen (повторное нажатие обновляет вердикт, не дублирует); событие LabelAdded; строка в `eval/datasets/relevance/v1.jsonl` (append-only)
- [ ] T113 [US2] Бот: обработчик callback_query (`label:<verdict>:hh:<id>`), подтверждение answerCallbackQuery, обновление клавиатуры; `/train` — счётчики размеченного и остаток до 30
- [x] T114 [P] [US2] [R-C3] Contract-тест: смена `LLM_MODEL_SCORING` в конфиге меняет модель в llm_call без правок кода (на записанных ответах)

## Phase 4: User Story 3 — Publish каждые 4 часа (P2)

- [ ] T115 [US3] Golden `publish_429.json`; красный contract-тест [S-C3]: 429/touch_limit → skip без ретрая, лог info, метрика publish_skipped, job success → `adapters/hh/publish.py` (PublisherPort)
- [ ] T116 [US3] `application/publish_resume.py` + worker-слот 4ч + `/publish`; DRY_RUN не вызывает HH ([F-I2]); метрика publish_skipped в `obs/metrics.py`

## Phase 5: User Story 4 — Переписка HH (P2)

- [ ] T117 [US4] Golden `negotiations.json`; красный contract-тест: непрочитанные за 24ч → NegotiationUpdate; пустой список → секции нет → `adapters/hh/negotiations.py` + `application/build_inbox_digest.py` + секция в рендере дайджеста

## Phase 6: User Story 5 — OAuth-хелпер (P3)

- [x] T118 [US5] `app/cli/oauth_hh.py`: интерактивный обмен кода на refresh token, список резюме (выбор HH_RESUME_ID), печать строк для .env; unit-тест логики обмена на respx; токены не логируются

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
