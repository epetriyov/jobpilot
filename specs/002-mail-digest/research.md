# Research: Работа с письмами (Этап 2)

## 1. Доступ к Gmail: REST + httpx, без официального SDK

- **Decision**: Gmail REST API напрямую через httpx: `GET /gmail/v1/users/me/messages?q=newer_than:1d`, `GET /messages/{id}?format=full`; OAuth Google — installed-app flow в CLI-хелпере (`app/cli/oauth_gmail.py`), scope строго `gmail.readonly`; access token обновляется по refresh token (паттерн [S-C2] этапа 1: 401 → refresh → повтор 1 раз).
- **Rationale**: google-api-python-client тянет тяжёлую цепочку зависимостей ради трёх REST-вызовов; httpx уже в стеке, respx-тесты единообразны с HH.
- **Alternatives**: официальный SDK (тяжело, свой транспорт — мимо respx); IMAP (нет ссылок на письма, сложнее OAuth).

## 2. Мок-режим (решение владельца)

- `GMAIL_MODE` (auto|fake|real), auto: real при наличии `GMAIL_REFRESH_TOKEN`. `FakeGmailInbox` — корпус ~15 реалистичных писем: ответ работодателя, приглашение на интервью, рассылка магазина, уведомление LinkedIn «wants to connect», письмо от hh.ru, спам — покрывает все ветки префильтра и секций. Каждый fetch добавляет 1–2 новых письма (паттерн FakeHhVacancySource).
- Стаб-классификатор для LLM_MODE=fake: детерминированный вердикт по маркерам (домены/ключевые слова) + шаблонный summary; llm_call пишется (O1).

## 3. Двухступенчатый фильтр (M1)

- Ступень 1, эвристика (домен/конфиг): whitelist-домены (`hh.ru`, `getmatch.ru`, `habr.com`, `linkedin.com`) → сразу кандидаты; blacklist-маркеры рассылок (`unsubscribe`+промо-ключи, `no-reply` магазинов из стоп-списка) → отсев без LLM; остальное → к LLM.
- Ступень 2, LLM: schema `MailVerdict {is_job: bool, summary: str ≤200, section: mail|linkedin}`; невалидно → 1 retry → фолбэк «unclassified» (письмо показывается с темой — принцип «ноль пропусков офферов» важнее ложных срабатываний, [M-E1]).
- LinkedIn-уведомления определяются эвристикой ДО LLM (домен linkedin.com + шаблоны тем) — LLM для них не нужен ([M-U3]).
- Письма-уведомления hh.ru НЕ показываются в «Почте» (уже покрыты секцией negotiations этапа 1) — только персист с пометкой, чтобы не потерять историю.

## 4. inbox_message и дедуп

- Таблица: id, gmail_id unique, source, sender, subject, summary, url, section, received_at, processed_at. Тело письма НЕ хранится (M4-производная). Дедуп повторных прогонов — по gmail_id.
- Ссылка на письмо: `https://mail.google.com/mail/u/0/#inbox/{gmail_id}`.

## 5. Eval mail_classify

- Датасет: `{"id": gmail_id, "input": {"sender", "subject", "snippet"}, "expected": {"is_job": bool, "section": ...}}`; наполняется мок-корпусом (сразу) и реальными обезличенными письмами (после кредов). Раннер: accuracy ≥0.9 + отдельный assert: false negative на письмах с маркером offer/interview = 0 (блокер [M-E1]).

## 6. Секции в дайджесте

- `BuildInboxDigest` (этап 1, negotiations) расширяется: рендер трёх секций — «Переписка HH» (negotiations API), «Почта» (gmail job-письма), «LinkedIn» (linkedin_gmail). Пустые секции скрываются. Сбой сбора почты изолируется (S4-паттерн): дайджест вакансий уходит в любом случае, job_run=partial.
