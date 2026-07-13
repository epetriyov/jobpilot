# Tasks: Работа с LinkedIn — полуавтомат (Этап 3)

**Input**: Design documents from `/specs/003-linkedin-invites/`

**Tests**: обязательны (constitution II): красный тест по кейсу TEST_CASES.md раздела 4 — до кода.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Foundational

- [ ] T301 Конфиг: `LINKEDIN_COMPANIES`, `LINKEDIN_ROLES`, `INVITES_CRON`, `INVITES_REMIND_DAYS`, `INVITE_STOP_PHRASES` (contracts/env.md)
- [ ] T302 [N-U1] Красные тесты → домен networking: `InviteDraft.transition` (proposed→sent→accepted, обратные → IllegalTransition), `InviteStatus`
- [ ] T303 [P] [N-C1]-домен: `build_pairs` (декартово − активные пары), `people_search_url` (percent-encoding, кириллица); [N-U2]: схема `InviteText` ≤300 → реджект
- [ ] T304 [N-U3] Grep-тест `test_no_linkedin_http.py`: в `app/` нет HTTP-обращений к linkedin.com (белый список: шаблон search_url в networking, маршрутизация писем в correspondence)
- [ ] T305 [F-I1] Миграция `0004_stage3`: linkedin_target + частичный uq-индекс + integration-тест

## Phase 2: US1 — еженедельный пакет (P1) 🎯 MVP

- [ ] T306 [US1] Стаб инвайт-текста в `adapters/llm/fake.py` (детерминированный, ≤300, компания упомянута) + промпт `invite_v1.md`
- [ ] T307 [US1] [N-C1] Contract-тест на фейках → `application/build_invite_batch.py`: 5×4 → ≤20, дедуп к активным, LLM-текст (невалидно → 1 retry → шаблон), persist, InviteBatchReady; llm_call (O1)
- [ ] T308 [US1] `InviteRepository` (persistence) + бот: рендер карточек `/invites`, worker: cron weekly_invites через run_job; DRY_RUN-пометка

## Phase 3: US2 — статусы кнопками (P1)

- [ ] T309 [US2] [N-U1] Тест → `application/update_invite_status.py` + колбэки `inv:sent:<id>`/`inv:accepted:<id>`; недопустимый переход → answerCallbackQuery «уже финальный», состояние неизменно; `/invites_status`

## Phase 4: US3 — напоминание (P2)

- [ ] T310 [US3] Тест → блок «неотправленные: N» в пакете при proposed старше порога; `/invites_pending`

## Phase 5: Eval и Polish

- [ ] T311 [N-E1] Датасет invite_rubric (append-only из прогонов) + judge-раннер (pass ≥0.9) — прогон после подключения реального LLM (хвост)
- [ ] T312 Гейты; quickstart; отчёт (DoD §7)
- [ ] T313 🖐 Владелец: проверка 5 заготовок, ручная отправка первой партии → закрытие этапа

## Dependencies

T301–T305 → T306–T308 → T309 → T310; T311 после T307 (датасет) и реального LLM.

## Соответствие кейсам TEST_CASES.md (раздел 4)

| Кейс | Задача |
|---|---|
| [N-U1] | T302, T309 |
| [N-U2] | T303, T307 |
| [N-U3] | T304 |
| [N-C1] | T303, T307 |
| [N-E1] | T311, T313 |
| [F-I1] | T305 |
