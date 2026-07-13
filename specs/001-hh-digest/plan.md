# Implementation Plan: Вся работа с HH — выгрузка в чат (Этап 1)

**Branch**: `001-hh-digest` | **Date**: 2026-07-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-hh-digest/spec.md`

## Summary

Первый боевой источник: адаптер HH (`VacancySourcePort`) с OAuth-хелпером и авто-refresh токена, use case `RunDailyDigest` (сбор по EM-запросам + similar → дедуп через seen-репозиторий → скоринг Flash-Lite через существующий `LlmPort` с few-shot из labeled_vacancy → карточки в Telegram с 👍/👎/🔗), `PublishResume` каждые 4 часа с обработкой 429, секция negotiations в дайджесте, команды `/digest`, `/publish`, `/train`. Eval-контекст `relevance` (precision/recall/F1) + обязательное сравнение Flash-Lite vs Flash. Строго TDD по TEST_CASES разделам 1–2; фундамент этапа 0 (домен, LlmPort, хранение, obs) переиспользуется без изменений домена.

## Technical Context

**Language/Version**: Python 3.12 (без изменений)

**Primary Dependencies**: без новых тяжёлых зависимостей: httpx (уже есть) — HH API; aiogram 3 — inline-кнопки/колбэки; APScheduler — cron 10:00 МСК и слот 4ч; instructor/openai — уже подключены

**Storage**: существующие таблицы + миграция `0002_stage1`: скор у seen_vacancy (для R1) и снапшот текста (для разметки из карточки); labeled_vacancy — без изменений схемы

**Testing**: golden-файлы реальных ответов HH (`tests/golden/hh/`), respx для HTTP-контрактов, фейковый LlmPort, testcontainers для интеграции; aiogram-хендлеры — прямые вызовы с фейковыми апдейтами (как [F-U2] этапа 0)

**Target Platform**: тот же compose (bot, worker, db, alloy); новых сервисов нет

**Project Type**: расширение существующего монорепо

**Performance Goals**: дневной объём ~100–300 вакансий; скоринг последовательный с обычными таймаутами — минуты, не критично

**Constraints**: HH API — соблюдение лимитов (без агрессивного параллелизма), User-Agent с контактом по правилам HH; refresh token только в env/локальном файле; CI — без ключей (golden + respx + записанные ответы)

**Scale/Scope**: один пользователь; ≤50 карточек/день; датасет relevance ≥30

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Слои | HH-логика в `adapters/hh/`; сценарии в `application/` (RunDailyDigest, ScoreVacancy, PublishResume, BuildInboxDigest); домен sourcing/shared НЕ меняется; relevance-правила (R1–R5) — `domain/relevance/`; import-linter гоняется как раньше | PASS |
| II. Test-first | Каждая задача tasks.md начинается с кейса TEST_CASES: [S-C1..C4], [R-U1..U5], [R-C1..C3], [X-I1]; golden-файлы — до адаптера | PASS |
| III. LLM — измеряемая зависимость | Скоринг только через LlmPort этапа 0; промпт `scoring_v1.md` уже версионирован; датасет relevance append-only + раннер с порогами [R-E1]; сравнение моделей — обязательный отчёт; модель — строка конфига | PASS |
| IV. Безопасность | HH-токены только env/локальный файл (не в git); санитайзер логов уже маскирует (добавить hh-токены в secret_values); DRY_RUN отключает publish и боевую отправку; тексты вакансий — data-блок (R5) | PASS |
| V. Наблюдаемость | Каждый job (digest, publish) через run_job (JobRun+span+trace_id); метрики уже есть (vacancies_discovered, digest_sent, llm_*, +publish_skipped) | PASS |
| VI. Человек в контуре | 3 дня DRY_RUN → разметка ≥30 → владелец явно включает боевой режим; publish уважает DRY_RUN | PASS |

Нарушений нет — Complexity Tracking не требуется.

## Project Structure

### Documentation (this feature)

```text
specs/001-hh-digest/
├── plan.md
├── research.md          # решения по HH API, OAuth, схеме скора
├── data-model.md        # миграция 0002: score у seen, снапшоты
├── quickstart.md        # ручная проверка этапа (DRY_RUN → боевой)
├── contracts/
│   ├── hh-api.md        # какие эндпоинты, маппинг, обработка 401/429
│   └── env.md           # новые переменные (HH_*, поисковые запросы)
└── tasks.md
```

### Source Code (изменения к структуре этапа 0)

```text
app/
├── domain/relevance/          # NEW: Score VO, правила R1–R5 (чистые)
│   ├── score.py               # Score(value, reason, prompt_version, model)
│   └── selection.py           # отбор в дайджест (порог/топ-50), few-shot «последние N»
├── ports/
│   ├── llm.py                 # без изменений
│   └── hh.py                  # NEW: HhPort (publish_resume, negotiations) — узкие операции вне VacancySourcePort
├── adapters/hh/               # NEW
│   ├── auth.py                # OAuth: refresh access token (401 → refresh → повтор 1 раз)
│   ├── client.py              # httpx-клиент, User-Agent, лимиты
│   ├── source.py              # VacancySourcePort: /vacancies по запросам + similar
│   ├── publish.py             # PublisherPort: /resumes/{id}/publish, 429 → skipped
│   ├── negotiations.py        # сообщения переписки за 24ч
│   └── mapping.py             # JSON HH → Vacancy ([S-C1])
├── application/
│   ├── score_vacancy.py       # NEW: ScoreVacancy (R1/R2/R3, llm+few-shot)
│   ├── run_daily_digest.py    # NEW: RunDailyDigest (сбор→дедуп→скоринг→карточки→seen)
│   ├── publish_resume.py      # NEW
│   └── build_inbox_digest.py  # NEW: секция negotiations
├── adapters/persistence/      # +ScoredVacancy колонки, репозиторий-методы
├── bot/                       # +карточки (InlineKeyboard), колбэки 👍/👎, /digest /publish /train
├── worker/                    # +jobs: daily_digest (cron 10:00 МСК), publish_resume (каждые 4ч)
└── cli/oauth_hh.py            # NEW: CLI-хелпер OAuth (запускается владельцем)

eval/
├── datasets/relevance/v1.jsonl   # наполняется разметкой (append-only)
└── runners/run.py                # +контекст relevance (P/R/F1, пороги, сравнение моделей)

tests/
├── golden/hh/                    # записанные ответы HH: search, similar, publish_429, negotiations
├── unit/domain/test_relevance.py # R-U1..R-U5
├── contract/test_hh_*.py         # S-C1..S-C4
└── integration/test_digest_flow.py  # X-I1 с HH-фикстурами
```

**Structure Decision**: HH-специфика изолирована в `adapters/hh/`; правила релевантности R1–R5 поднимаются в чистый `domain/relevance/` (пере используются любым источником этапов 4–5). `PublisherPort` этапа 0 получает первую боевую реализацию. Бот остаётся тонким: колбэк 👍 → use case `LabelVacancy`.

## Сверка с DOMAIN.md

- Термины: `Score`, `Label`, `VacancyScored`, `LabelAdded`, `ResumePublish` — дословно из §1/§3.2.
- Инварианты R1–R5 (§3.2) — доменные тесты [R-U1..U5]; S1–S4 уже покрыты этапом 0.
- Порты §3.2: `LlmPort.score(profile, fewshot, vacancy_text) -> Score` реализуется поверх generic `LlmPort.complete` (response_model=Score) — без изменения контракта этапа 0.
- Хранение §4: минимальный слой; скор к seen_vacancy — уточнение реализации дедупа/R1, полное `vacancy` остаётся этапом 6. Обновления DOMAIN.md не требуется (домен не расширился — только реализация).

## Сверка с AGENT_GUIDE.md

- §4: скоринг — pydantic Score(0..100, reason≤200), max_retries=1, graceful skip; промпт остаётся `scoring_v1` (изменение текста → v2 + eval).
- §6 «Новый источник»: кейсы → golden → адаптер → конфиг источников → canary (первый источник = сразу основной, canary-механика включается со 2-го источника, этап 4) → датасет.
- §7 DoD: кейсы разделов 1–2 зелёные; eval-отчёты закоммичены; ручная проверка 3 дня DRY_RUN.
