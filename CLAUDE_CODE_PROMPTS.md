# CLAUDE_CODE_PROMPTS.md — готовые промпты для Claude Code (Fable 5)

> Как пользоваться: положите все файлы пакета в пустой репозиторий (структура ниже), откройте Claude Code в его корне и вставляйте промпты по порядку. Один этап = одна сессия (или /clear между этапами) — контекст остаётся чистым, вся память проекта в md-файлах и спеках.

Структура репозитория перед стартом:
```
PLAN.md
docs/DOMAIN.md  docs/TEST_CASES.md  docs/AGENT_GUIDE.md
memory/constitution.md
resumes/resume_em.md            ← источник фактов для писем (уже в пакете)
resumes/cover_letter_guide.md   ← структура/тон/акценты + белый список метрик (уже в пакете)
```

---

## Промпт 0 — бутстрап (этап 0: фундамент и DevEx)

```
Прочитай в этом порядке: PLAN.md, docs/DOMAIN.md, docs/AGENT_GUIDE.md, docs/TEST_CASES.md, memory/constitution.md. Это источники истины проекта JobPilot; constitution — высший приоритет.

Затем выполни этап 0 из PLAN.md (§6):
1. Инициализируй spec-kit в текущем репозитории (specify init --here, агент claude); перенеси memory/constitution.md в положенное spec-kit место, не меняя содержания.
2. Пройди spec-kit цикл для этапа 0: /speckit.specify по описанию этапа 0 из PLAN.md → /speckit.plan (сверься с DOMAIN.md и AGENT_GUIDE.md) → /speckit.tasks (каждая задача ссылается на кейсы из TEST_CASES.md, раздел 0).
3. Реализуй строго по TDD: каркас репозитория по PLAN.md §4, docker compose (bot, worker, db), домен shared+sourcing, минимальный слой хранения (seen_vacancy, labeled_vacancy, llm_call, job_run — см. DOMAIN.md §4), LlmPort через instructor + адаптер OpenRouter (instructor, openai-режим, модели из конфига) + фейковый провайдер, structlog + OTel SDK → контейнер Grafana Alloy → Grafana Cloud, базовый дашборд и алерты Grafana Alerting в мой Telegram (job failed, дайджест не отправлен к 10:15, scraper_failures), DRY_RUN, backup.sh, каркас eval/, Makefile (up/down/test/eval/lint/migrate/backup).
4. Настрой GitHub: .github/workflows/ci.yml (ruff, mypy, import-linter, unit+contract тесты, eval на записанных ответах — без ключей), интеграцию anthropics/claude-code-action для авторевью PR, deploy.yml (по тегу, SSH на VPS, секреты из GitHub Secrets).
5. Всё, что требует моих данных (TELEGRAM_API_TOKEN, OWNER_CHAT_ID, OPENROUTER_API_KEY, GRAFANA_CLOUD_OTLP_ENDPOINT + INSTANCE_ID + API_TOKEN (free-аккаунт Grafana Cloud заведу я — запроси креды), SSH-доступ) — оформи как .env.example и явно запроси у меня значения; ничего не выдумывай.

Заверши отчётом: что сделано, статус acceptance-критериев этапа 0, инструкция для моей ручной проверки (Definition of Done — AGENT_GUIDE.md §7).
```

## Универсальный шаблон промпта этапа N (1–7)

```
Продолжаем JobPilot. Перечитай PLAN.md, docs/DOMAIN.md, docs/AGENT_GUIDE.md, docs/TEST_CASES.md, memory/constitution.md и спеки предыдущих этапов в specs/.

Выполни этап <N> («<название из PLAN.md>»):
1. /speckit.specify по описанию этапа из PLAN.md §6 → /speckit.plan → /speckit.tasks (задачи ссылаются на кейсы TEST_CASES.md раздела <X>).
2. Реализация строго по TDD; правила слоёв и LLM — AGENT_GUIDE.md.
3. Прогони eval этапа (make eval CONTEXT=<...>), зафиксируй отчёт в eval/reports/ и сравни с предыдущим, если он есть.
4. Если домен уточнился — обнови DOMAIN.md и TEST_CASES.md в том же PR.
5. Данные и доступы (токены, id, эндпоинты) запрашивай у меня или делай CLI-хелперы — не выдумывай.

Заверши отчётом: сделано / acceptance / eval-метрики / что нужно от меня для ручной проверки.
```

## Конкретизация по этапам (вставлять в шаблон)

**Этап 1 — вся работа с HH** (кейсы: разделы 1-HH и 2). Особое: CLI-хелпер OAuth HH (запроси у меня client_id/secret и resume_id); скоринг Flash-Lite через instructor, few-shot «последние N» из labeled_vacancy; карточки только с 👍/👎/🔗; publish каждые 4 часа; ОБЯЗАТЕЛЬНО: после моей разметки ≥30 вакансий — сравнительный eval Flash-Lite vs Flash (google/gemini-2.5-flash-lite vs google/gemini-2.5-flash через OpenRouter) на датасете relevance, отчёт с рекомендацией. Боевой режим не включай — только DRY_RUN до моей команды.

**Этап 2 — работа с письмами (входящие)** (кейсы: раздел 3, кроме помеченных «этап 6»). Особое: CLI-хелпер Gmail OAuth (gmail.readonly, запроси credentials.json); эвристический префильтр до LLM; секции «Почта» и «LinkedIn» в дайджесте; собери у меня ≥40 писем для датасета mail_classify (попроси переслать/выгрузить примеры).

**Этап 3 — работа с LinkedIn (полуавтомат)** (кейсы: раздел 4). Особое: запроси у меня список целевых компаний и ролей; grep-тест на отсутствие HTTP-вызовов к linkedin.com обязателен; еженедельный job — понедельник 10:00 МСК.

**Этап 4 — работа с GetMatch** (кейсы: раздел 1, S-C5/S-C6, S-E1). Особое: отдельный контейнер userbot; запроси у меня api_id/api_hash второго Telegram-аккаунта и проведи интерактивный логин Telethon через CLI-хелпер; сначала DRY_RUN-накопление корпуса сообщений для датасета getmatch_parse, потом парсер по TDD; canary 2 дня.

**Этап 5 — работа со скрейперами** (кейсы: раздел 1, S-C7…S-C10, S-E2). Особое: для каждого из 7 сайтов сначала исследуй network-запросы карьерного портала и покажи мне найденный JSON-эндпоинт или обоснуй Playwright; golden-файлы — из реальных ответов; canary 3 дня на сайт, включение — только моей командой /approve_scraper.

**Этап 6 — CRM, хранилище, письма, MCP (финальная фича)** (кейсы: разделы 5, 6, помеченные «этап 6» из раздела 3, R-E2). Особое: миграция минимального слоя на полное vacancy без потери разметки; статусная машина строго по DOMAIN.md §3.3 (property-тесты до реализации); сопроводительные письма — LLM_MODEL_LETTERS (Pro): структура/тон/акценты из resumes/cover_letter_guide.md, факты ТОЛЬКО из resumes/resume_em.md, hallucination-check по белому списку метрик из гайда (метрики из раздела «чего быть не должно» — автоматический реджект); семантический few-shot селектор (pgvector) + сравнительный eval против «последних N»; MCP-сервер на FastMCP по DOMAIN.md §3.7 + инструкция подключения к Claude Desktop через SSH-туннель.

**Этап 7 — прод-закалка** (кейсы: X-I1, X-I2, X-U1). Особое: systemd unit, healthchecks, README с процедурами (деплой с нуля, restore, ротация секретов, все OAuth-флоу), проверка deploy.yml end-to-end на реальном VPS.

## Служебные промпты

**Смена модели скоринга** (после сравнительного eval):
```
Переключи скоринг на <модель>: только конфиг LLM_MODEL_SCORING и прайсы, код не трогай. Прогони contract-suite R-C2 и make eval CONTEXT=relevance, приложи сравнение отчётов до/после.
```

**Разбор регресса качества подбора:**
```
Agreement rate упал (см. последние /review). Возьми расхождения из labeled_vacancy за период, сгруппируй по причинам ошибок скоринга, предложи правку промпта как новую версию, прогони eval на relevance и покажи diff метрик. Ничего не мержи без моего решения.
```

**Новая фича после MVP:**
```
Новая фича: <описание>. Действуй по spec-kit: /speckit.specify → /speckit.plan → /speckit.tasks, сверься с constitution и DOMAIN.md; если фича меняет домен — сначала PR с обновлением DOMAIN.md/TEST_CASES.md на моё утверждение, потом реализация по TDD.
```
