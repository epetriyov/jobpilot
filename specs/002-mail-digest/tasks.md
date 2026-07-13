# Tasks: Работа с письмами — входящие в дайджест (Этап 2)

**Input**: Design documents from `/specs/002-mail-digest/`

**Tests**: обязательны (constitution II): красный тест по кейсу TEST_CASES.md раздела 3 — до кода. Golden — до адаптера.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Foundational

- [x] T201 Конфиг: `GMAIL_MODE`, `GMAIL_*`-креды (SecretStr → санитайзер, [X-U1]), `MAIL_WHITELIST_DOMAINS`, `MAIL_BODY_LIMIT` (contracts/env.md); тест маскирования
- [x] T202 [F-I1] Миграция `0003_stage2`: inbox_message (data-model.md) + integration-тест идемпотентности и колонок
- [x] T203 [P] Домен correspondence (красные [M-U1] [M-U3] → реализация): `prefilter()` — whitelist/blacklist/linkedin-маршрутизация/hh-hidden; `InboxMessage` VO; `MailVerdict` схема с лимитом summary ([M-U2], M2)

## Phase 2: US1 — секция «Почта» (P1) 🎯 MVP

- [x] T204 [US1] Мок-корпус: `adapters/gmail/fake.py` (FakeGmailInbox, ~15 писем всех веток: работодатель, интервью, рассылка, linkedin, hh-уведомление; новые письма на fetch) + стаб-классификатор в `adapters/llm/fake.py`; тесты детерминизма
- [x] T205 [US1] [M-U2] Красный тест → промпт `mail_classify_v1.md` + use case `classify_inbox.py`: префильтр → LLM (data-блок, R5) → InboxMessage; невалидный выход → 1 retry → unclassified-фолбэк (письмо не теряется); llm_call (O1)
- [x] T206 [US1] [M-C1] Красный тест: обработаны только письма за 24ч; повторный прогон не дублирует (gmail_id-дедуп) → `InboxMessageRepository`
- [x] T207 [US1] [M-C2] Красный тест: тело письма отсутствует в логах тестового прогона (M4) — прогон classify_inbox с логгером в тестовом режиме
- [~] T208 (рендер и wiring готовы; e2e-прогон в Telegram — владелец) [US1] Секция «Почта» в дайджесте: расширение `build_inbox_digest.py` + рендер в боте; пустая секция скрыта; сбой сбора почты → digest partial, вакансии не страдают (S4-паттерн)

## Phase 3: US2 — секция «LinkedIn» (P2)

- [x] T209 [US2] [M-U3] Красный тест: «X wants to connect» → source=linkedin_gmail, секция «LinkedIn», не «Почта»; рендер секции

## Phase 4: US3 — реальный Gmail (P2, после кредов владельца)

- [ ] T210 [US3] Golden `tests/golden/gmail/` (messages_list, message_full, token_refresh — реальные обезличенные) → contract-тесты → `adapters/gmail/{auth,client,source}.py` (401 → refresh → повтор 1 раз; scope readonly)
- [ ] T211 [US3] `app/cli/oauth_gmail.py` (installed-app flow, печать строк .env); respx-тест обмена; токены не логируются

## Phase 5: Eval и Polish

- [ ] T212 [M-E1] Раннер `mail_classify`: accuracy ≥0.9 + false negative offer/interview = 0 (блокер); датасет из мок-корпуса сразу, реальные письма добавляются после кредов
- [ ] T213 Гейты зелёные; quickstart актуален; отчёт (DoD §7)
- [ ] T214 🖐 Владелец: 2 дня сверки summary с оригиналами → закрытие этапа

## Dependencies

- T201–T203 блокируют всё; T204 → T205 → T206/T207 → T208 → T209; T210–T211 независимы (ждут кредов); T212 после T204.

## Соответствие кейсам TEST_CASES.md (раздел 3)

| Кейс | Задача |
|---|---|
| [M-U1] | T203 |
| [M-U2] | T203, T205 |
| [M-U3] | T203, T209 |
| [M-C1] | T206 |
| [M-C2] | T207 |
| [M-E1] | T212, T214 |
| [F-I1] | T202 |
| [X-U1] | T201 |
