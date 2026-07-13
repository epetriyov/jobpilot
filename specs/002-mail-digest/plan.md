# Implementation Plan: Работа с письмами — входящие в дайджест (Этап 2)

**Branch**: `002-mail-digest` | **Date**: 2026-07-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-mail-digest/spec.md`

## Summary

Контекст CORRESPONDENCE (DOMAIN.md §3.4): адаптер Gmail (`InboxPort.fetch_since(dt)`) с OAuth-хелпером и мок-режимом `GMAIL_MODE` (паттерн этапа 1), двухступенчатая классификация (эвристический префильтр по доменам/ключевым словам → LLM «про работу?» + summary ≤2 строк через существующий `LlmPort`), персист в `inbox_message` (миграция 0003), сборка секций «Почта» и «LinkedIn» use case'ом `BuildInboxDigest` и включение их в утренний дайджест этапа 1. Eval-контекст `mail_classify` (accuracy ≥0.9, ноль пропусков офферов). Тела писем — нигде, кроме промпта (data-блок) и снапшота summary.

## Technical Context

**Language/Version**: Python 3.12 (без изменений)

**Primary Dependencies**: Gmail API — чистый httpx (REST + OAuth Google, refresh token), без тяжёлого google-api-python-client; остальное — существующий стек

**Storage**: миграция `0003_stage2`: таблица `inbox_message` (DOMAIN.md §4)

**Testing**: golden-файлы Gmail REST (`tests/golden/gmail/`), respx, мок-корпус писем для GMAIL_MODE=fake; фейковый LlmPort со стаб-классификатором

**Target Platform**: тот же compose; новых сервисов нет

**Project Type**: расширение монорепо

**Performance Goals**: десятки писем/день; последовательная обработка

**Constraints**: scope только gmail.readonly; тела писем не логируются (M4) и не хранятся в БД; CI без ключей (golden + respx); префильтр до LLM (M1 — экономия токенов)

**Scale/Scope**: один ящик владельца; ≤100 писем/сутки

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Слои | Gmail-грязь в `adapters/gmail/`; правила классификации (префильтр, маршрутизация секций) — `domain/correspondence/`; сценарий — `application/build_inbox_digest.py`; бот/worker не меняют толщину | PASS |
| II. Test-first | Кейсы [M-U1]–[M-U3], [M-C1], [M-C2] — красные тесты до кода; golden до адаптера | PASS |
| III. LLM | Классификация через LlmPort; промпт `mail_classify_v1.md`; схема выхода (job: bool, summary ≤2 строк); датасет mail_classify append-only + раннер с порогами; модель `LLM_MODEL_SUMMARY` из конфига | PASS |
| IV. Безопасность | Тела писем: не в логах ([M-C2]-тест), не в БД (только summary/метаданные), в промпте — data-блок (R5); gmail-креды — SecretStr + санитайзер; scope readonly | PASS |
| V. Наблюдаемость | Сбор почты — шаг дайджест-job'а (child span, изоляция сбоя → partial); метрики inbox_messages_total{section}, llm_* уже есть | PASS |
| VI. Человек в контуре | Только чтение почты; никаких ответов/действий с письмами; ручная сверка summary 2 дня до закрытия этапа | PASS |

## Project Structure

```text
specs/002-mail-digest/   plan.md research.md data-model.md contracts/ quickstart.md tasks.md

app/
├── domain/correspondence/     # NEW: InboxMessage VO, префильтр (M1), маршрутизация секций (M-U3)
├── ports/inbox.py             # NEW: InboxPort.fetch_since(dt) -> list[RawEmail]
├── adapters/gmail/            # NEW: auth.py (OAuth Google), client.py, source.py, fake.py (мок-корпус)
├── adapters/llm/prompts/mail_classify_v1.md   # NEW: промпт классификации+summary
├── application/
│   ├── classify_inbox.py      # NEW: префильтр → LLM → InboxMessage (persist)
│   └── build_inbox_digest.py  # расширение: секции «Почта»/«LinkedIn» в рендер дайджеста
├── adapters/persistence/      # +InboxMessageRepository, миграция 0003_stage2
└── cli/oauth_gmail.py         # NEW: хелпер (device/installed-app flow, печать строк .env)

eval/datasets/mail_classify/v1.jsonl   # append-only (мок-корпус + реальные обезличенные)
tests/golden/gmail/                    # messages_list.json, message_full.json, token_refresh.json
```

**Structure Decision**: зеркало этапа 1 — доменные правила чистые, грязь в адаптере, мок как полноправная реализация порта. `BuildInboxDigest` уже существует для negotiations HH (этап 1) — расширяется секциями, а не дублируется.

## Сверка с DOMAIN.md / AGENT_GUIDE.md

- Термины §3.4 дословно: `InboxMessage(source: gmail|hh|linkedin_gmail, subject, summary, url, received_at)`; инварианты M1 (префильтр до LLM), M2 (summary ≤2 строк), M4 (тела не логируются) — тесты [M-U1], [M-U2], [M-C2].
- Порты §3.4: `InboxPort.fetch_since(dt)`, `LlmPort.classify_and_summarize` — реализуется поверх generic `LlmPort.complete` (response_model=MailVerdict), контракт LlmPort не меняется.
- §4: inbox_message — таблица этапа (миграция 0003), тело письма не хранится.
- Новая LLM-задача по чек-листу AGENT_GUIDE §6: термин в DOMAIN есть → кейсы в TEST_CASES есть (раздел 3) → метод/промпт v1 → датасет+раннер → use case → UI-секция.
