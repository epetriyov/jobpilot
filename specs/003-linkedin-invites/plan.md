# Implementation Plan: Работа с LinkedIn — полуавтомат (Этап 3)

**Branch**: `003-linkedin-invites` | **Date**: 2026-07-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-linkedin-invites/spec.md`

## Summary

Контекст NETWORKING (DOMAIN.md §3.5): чистый агрегат `InviteDraft` со статусной машиной proposed→sent→accepted (N3), генератор еженедельного пакета (декартово произведение конфиг-списков компаний×ролей, дедуп к неотправленным, [N-C1]), персонализированные тексты ≤300 знаков через LlmPort со стабом (N2, [N-U2]), people-search URL с корректным кодированием, кнопки статусов и команды в боте, напоминание о proposed. Никакого HTTP к linkedin.com — гарантируется статическим grep-тестом ([N-U3]). Хранение — таблица linkedin_target (миграция 0004). Eval `invite_rubric` (LLM-as-judge) — после подключения реального LLM.

## Technical Context

**Language/Version / Dependencies / Storage / Testing / Platform**: без изменений (стек этапов 0–2); новых зависимостей нет

**Storage**: миграция `0004_stage3`: linkedin_target (InviteDraft + таймстемпы статусов)

**Constraints**: ноль сетевых вызовов к linkedin.com (N1); тексты без ПД адресатов (только роль+компания); CI без ключей

**Scale/Scope**: ≤20 заготовок/неделю (5 компаний × 4 роли по умолчанию)

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Слои | Статусная машина и генерация пар — `domain/networking/` (метод агрегата, не if-ы в боте — AGENT_GUIDE §1); use cases `application/{build_invite_batch,update_invite_status}.py`; бот тонкий | PASS |
| II. Test-first | [N-U1] (переходы), [N-U2] (лимит 300 + retry), [N-C1] (декартово+URL-кодирование), [N-U3] (grep linkedin.com) — красные до кода | PASS |
| III. LLM | Промпт `invite_v1.md`; схема InviteText(text ≤300); стаб для LLM_MODE=fake; датасет invite_rubric + judge-раннер (после реального LLM); llm_call (O1) | PASS |
| IV. Безопасность | N1 — grep-тест как инвариант анти-ToS (constitution IV прямо запрещает автоматизацию LinkedIn); ПД адресатов не собираются | PASS |
| V. Наблюдаемость | job weekly_invites через run_job; метрика invite_drafts_total{status} | PASS |
| VI. Человек в контуре | Отправка только вручную владельцем; система лишь готовит текст и ссылку | PASS |

## Project Structure

```text
app/
├── domain/networking/         # NEW: InviteDraft (transition N3, IllegalTransition), build_pairs (декартово+дедуп), search_url()
├── ports/networking.py        # NEW: InviteRepositoryPort
├── adapters/persistence/      # +InviteRepository, миграция 0004_stage3
├── adapters/llm/prompts/invite_v1.md
├── application/
│   ├── build_invite_batch.py  # NEW: пары → LLM-текст (retry→шаблон) → persist → пакет в чат + напоминание
│   └── update_invite_status.py# NEW: колбэк кнопки → transition → persist
├── bot/                       # +/invites, /invites_pending, /invites_status, колбэки inv:<action>:<id>
└── worker/                    # +job weekly_invites (cron конфиг, понедельник)

tests/unit/domain/test_networking.py    # N-U1, N-U2-схема, URL, пары
tests/unit/test_no_linkedin_http.py     # N-U3 grep-тест
tests/contract/test_invite_batch.py     # N-C1 на фейках
```

**Structure Decision**: зеркало предыдущих этапов; стаб инвайт-текста — третья фабрика в adapters/llm/fake.py (паттерн scoring/mail).

## Сверка с DOMAIN.md / AGENT_GUIDE.md / TEST_CASES.md

- Термины §3.5 дословно: `InviteDraft(title, company, search_url, invite_text, status)`, `InviteBatchReady`; инварианты N1–N3 → тесты [N-U1]–[N-U3], [N-C1]; eval [N-E1].
- §4: linkedin_target — таблица этапа, одна миграция.
- Статусная машина — метод `InviteDraft.transition(to)` с доменной ошибкой `IllegalTransition` (термин из §1/§3.3 — переиспользуем имя для единообразия ошибок переходов).
- Чек-лист «Новая LLM-задача» AGENT_GUIDE §6: термин есть → кейсы есть → промпт v1 → датасет invite_rubric (+judge) → use case → UI-кнопки.
