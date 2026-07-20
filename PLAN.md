# PLAN.md — JobPilot: Telegram-агент поиска работы (финальная версия v4)

> Стартовый документ для coding-агента. Порядок чтения: PLAN.md → docs/DOMAIN.md → docs/AGENT_GUIDE.md → docs/TEST_CASES.md → memory/constitution.md.
> Методология: Spec-Driven Development (GitHub spec-kit) + Domain-Driven Design + Test-Driven Development.
> Архитектурная диаграмма основных узлов утверждена пользователем: источники (HH, GetMatch-бот, 7 сайтов, Gmail) → VPS/Docker (userbot, worker, bot, PostgreSQL, Langfuse, MCP-сервер с этапа 6) → внешние сервисы (Gemini API, Telegram, OTel-коллектор пользователя, GitHub с CI и агентом-ревью).

---

## 1. Роль исполнителя

Ты — senior-инженер. Каждый этап проходит spec-kit цикл (`/speckit.specify → /speckit.plan → /speckit.tasks`), реализация — строго TDD по docs/TEST_CASES.md. Не переходи к следующему этапу без: зелёных тестов, eval-отчёта, ручной проверки пользователем. Секреты — только env. Действия с риском нарушения ToS (автоматизация LinkedIn, обход капчи) — эскалация пользователю.

## 2. Зафиксированные параметры

| Параметр | Решение |
|---|---|
| Ранние этапы (1–5) | ТОЛЬКО выгрузка релевантных вакансий/писем в чат-бот. Без CRM-операций. Минимальный слой хранения: реестр виденных (дедуп), размеченные вакансии 👍/👎 (few-shot), llm_call (затраты) |
| Финальная фича (этап 6) | Полное хранилище вакансий + CRM-операции (сохранить/статусы/удалить/статистика) + сопроводительные письма + MCP-сервер |
| LLM по умолчанию | Доступ ко всем моделям — через **OpenRouter** (OpenAI-совместимый API, один ключ). Скоринг/классификация/summary — `google/gemini-2.5-flash-lite`; письма (этап 6) — `google/gemini-2.5-pro` |
| Свап моделей | Первоклассная возможность: LlmPort + **instructor** в openai-режиме поверх OpenRouter; модель per-purpose — строка в конфиге (`LLM_MODEL_SCORING`, `LLM_MODEL_LETTERS`, ...), свап = смена строки без кода. `cost_usd` в llm_call — фактический из ответа OpenRouter (прайсы конфига — фолбэк). На этапе 1 — обязательный eval Flash-Lite vs Flash на размеченном датасете |
| LinkedIn | Полуавтомат: заготовки инвайтов, отправка вручную; входящие — через Gmail-уведомления |
| HH источники (пересмотр 2026-07-17) | HH API недоступен; userbot (my.telegram.org отдаёт ERROR при создании api_id) и web-скрейп (анти-бот/VPN-стена) заблокированы. **Основной источник — email**: HH шлёт подборки «Вакансии по подписке» на почту, парсим через уже подключённый Gmail. Адаптер `HhEmailSource(VacancySourcePort)` над `InboxPort`; `parse_hh_email` — чистая функция над HTML письма. `HH_SOURCES=email`. userbot/web — опциональные хвосты (включатся, если каналы разблокируются). Обход анти-бота/капчи не строим (S5). Домен Sourcing не меняется |
| GetMatch | Userbot (Telethon), второй Telegram-аккаунт (общий с HH-ботом) |
| Publish резюме HH | Каждые 4 часа, авто-клик «поднять» через Playwright (API нет); лимит HH → publish_skipped; уважает DRY_RUN. Действие-запись на сайт: осознанное решение владельца, каждое действие логируется |
| Почта | Gmail API, `gmail.readonly`, refresh token |
| Сайты | Прямые скрейперы: Yandex, VK, Avito, Т-Банк, Ozon, Альфа, Сбер |
| Релевантность | Резюме Engineering Manager, один скор; фильтры зарплаты/стоп-слов выключены (конфиг на будущее); дайджест ≤50/день, score ≥ 60 |
| GitHub | Репозиторий + Actions (ruff, mypy, import-linter, unit+contract тесты, eval на записанных ответах LLM) + агент-ревьюер `anthropics/claude-code-action` + deploy-workflow по тегу (SSH) |
| Spec-kit | Инициализируется на этапе 0 (`specify init --here`); constitution — `memory/constitution.md`; каждый этап = feature |
| Мониторинг | structlog JSON + OpenTelemetry → **Grafana Alloy** (контейнер в compose: OTLP от сервисов + метрики VPS/docker) → **Grafana Cloud Free** (метрики/логи/трейсы, retention 14 дней); алерты Grafana Alerting → Telegram владельца. LLM-observability — Langfuse self-hosted + таблица llm_call (долгосрочная история — в своём Postgres) |
| CRM-статусы (этап 6) | новое → отклик → собес (раунды hr, tech-1, …, final) → оффер / отказ (до hr, hr, tech, final) |
| Пользователь | Один, OWNER_CHAT_ID; расписание — 10:00 МСК (Europe/Moscow) |
| Бэкапы | pg_dump ежедневно, ротация 14 дней |

## 3. Стек

Python 3.12 · aiogram 3 · APScheduler · httpx · **instructor + openai-SDK (base_url OpenRouter)** · Telethon · Playwright (только где сайт не отдаёт JSON) · SQLAlchemy 2 + Alembic · PostgreSQL 16 + pgvector · structlog · OpenTelemetry SDK · Langfuse · FastMCP (этап 6) · Docker Compose · GitHub Actions + claude-code-action · spec-kit · Ubuntu VPS (VDSina), systemd.

## 4. Архитектура

Гексагональная, bounded contexts — в docs/DOMAIN.md. Правила слоёв (import-linter, нарушение = провал CI): `domain` без I/O и внешних импортов; `application` (use cases) ← domain+ports; `adapters` реализуют ports; `bot`/`worker`/`mcp` — тонкие интерфейсные слои поверх application.

```
jobpilot/
  .github/workflows/   ci.yml (lint+tests+recorded-eval, claude-code review) · deploy.yml (по тегу, SSH)
  .specify/ + memory/constitution.md      # spec-kit
  specs/<NNN-feature>/ spec.md plan.md tasks.md   # по одному на этап
  app/
    domain/       sourcing/ relevance/ crm/ correspondence/ networking/ shared/
    ports/        VacancySourcePort, LlmPort, InboxPort, NotifierPort, Repository-порты
    adapters/     hh/{email_source, telegram_source, web_source, web_publish} getmatch/ sites/×7 gmail/ telegram/ telegram_userbot/ (Telethon) llm/{instructor_openrouter, fake}/ persistence/
    application/  use cases: RunDailyDigest, ScoreVacancy, PublishResume, BuildInboxDigest,
                  BuildInviteBatch, SaveVacancy*, ChangeStatus*, GenerateCoverLetter* (*— этап 6)
    bot/ worker/ mcp/ obs/
  eval/ datasets/ runners/ reports/
  docs/ DOMAIN.md TEST_CASES.md AGENT_GUIDE.md
  tests/ unit/ contract/ integration/ golden/
  resumes/ deploy/ PLAN.md
```

**LLM-слой (свап моделей).** Все вызовы — через `LlmPort`; реализация — instructor в openai-режиме с `base_url=https://openrouter.ai/api/v1` и ключом `OPENROUTER_API_KEY`: pydantic-модель как response_model, валидационные ретраи (max_retries=1, затем graceful skip по инварианту R2). Модель per-purpose — строка из конфига; свап модели/провайдера = смена строки. `cost_usd` берётся из фактического usage ответа OpenRouter; прайсы конфига — фолбэк. Прямой адаптер провайдера (мимо OpenRouter) — допустимое расширение через тот же LlmPort. Промпты версионируются файлами. Ключи в промпты не попадают; внешние тексты — недоверенные данные (anti-prompt-injection).

**MCP-сервер (этап 6).** FastMCP поверх use cases: read-инструменты (`list_vacancies`, `get_vacancy`, `search_saved`, `get_costs`, `funnel_stats`) + белый список write (`set_status`, `run_digest(dry_run)`). Auth-токен, доступ только localhost/SSH-туннель, отдельная ограниченная роль БД, нулевой доступ к секретам интеграций. Подключается к Claude Desktop/Code: диалоговые запросы к базе, подготовка к собесам, отладка.

**Docker compose:** bot, worker, alloy (Grafana Alloy: OTLP-приём + метрики хоста/docker → Grafana Cloud), userbot (этап 4+), db, langfuse (профиль), mcp (профиль, этап 6). Postgres/Langfuse/MCP наружу не публикуются; UFW — только 22; бот — long polling.

## 5. Eval-harness (сквозной)

`eval/datasets/<name>/vN.jsonl` (append-only) · `make eval CONTEXT=<name>` → метрики + отчёт в `eval/reports/` + Langfuse dataset run · пороги из TEST_CASES.md зашиты в раннеры · любое изменение промпта или смена модели = новая версия + обязательный прогон + сравнение отчётов в PR · CI гоняет eval на записанных ответах LLM (без ключей и токенов), полноценные прогоны — локально/на VPS · каждый вызов LLM → Langfuse trace + строка llm_call (модель, prompt_version, токены, cost_usd по прайсу из конфига, latency, trace_id).

## 6. Этапы

Каждый этап: spec-kit цикл → TDD → ✅ acceptance → eval-отчёт → 🖐 ручная проверка пользователем → обновление DOMAIN/TEST_CASES при уточнении домена.

### Этап 0. Фундамент и DevEx
GitHub-репозиторий; spec-kit init + constitution; Actions CI (ruff, mypy, import-linter, unit+contract, recorded-eval) + claude-code-action ревью + deploy.yml; compose (bot, worker, db, **alloy**); домен shared+sourcing (TDD); минимальный слой хранения: `seen_vacancy` (SourceRef+hash+first_seen), `labeled_vacancy` (снапшот текста, вердикт, embedding-колонка), `llm_call`, `job_run`; LlmPort + instructor-адаптер OpenRouter + фейковый провайдер для тестов; structlog + OTel SDK → Alloy → Grafana Cloud (env: `GRAFANA_CLOUD_OTLP_ENDPOINT`, `GRAFANA_CLOUD_INSTANCE_ID`, `GRAFANA_CLOUD_API_TOKEN`); базовый дашборд (job'ы, вакансии по источникам, LLM-токены/стоимость) и алерты Grafana Alerting → Telegram (job failed, дайджест не отправлен к 10:15 МСК, scraper_failures); DRY_RUN; backup.sh; каркас eval/.
✅ CI зелёный на PR, агент-ревью постит комментарии; compose с нуля; бот отвечает только владельцу; телеметрия видна в Grafana Cloud (трейс + метрики + логи), тестовый алерт доходит в Telegram; `make eval` работает.
🖐 Пользователь: заводит free-аккаунт Grafana Cloud и передаёт креды, видит дашборд и тестовый алерт, сообщение бота, ревью-комментарий агента в тестовом PR.

### Этап 1. Вся работа с HH (только выгрузка в чат)
> Пересмотр 2026-07-15: API HH недоступен — источники изменены на userbot + web-скрейпер, поднятие резюме — Playwright-клик.
> Пересмотр 2026-07-17: userbot и web заблокированы (api_id не создаётся; анти-бот/VPN-стена). **Основной источник — email** (письма HH «Вакансии по подписке» через Gmail, `HhEmailSource`). Домен, дедуп, скоринг, дайджест, разметка — без изменений.

Доступ: подписка на рассылку вакансий HH + подключённый Gmail (этап 2); сбор из писем «Вакансии по подписке» (`HH_SOURCES=email`); дедуп по seen; скоринг Flash-Lite через instructor (few-shot «последние N» из labeled_vacancy); карточки в чат: кнопки 👍/👎/🔗 (💾 и ✉️ — этап 6); `/train`; `/digest`. Хвосты userbot/web (поднятие резюме Playwright-кликом, raw-секция непарсенного) — опциональны, включатся при разблокировке каналов.
Eval: датасет `relevance` ≥30 размеченных (собрать в DRY_RUN); **обязательное сравнение Flash-Lite vs Flash** — если ΔF1 незначима, остаёмся на Lite; отчёт в eval/reports/.
✅ 10:00 → ≤50 карточек; 429 на publish обработан; невалидный выход LLM не роняет пайплайн; каждый вызов в llm_call/Langfuse.
🖐 3 дня DRY_RUN, разметка ≥30 вакансий, явное включение боевого режима.

### Этап 2. Работа с письмами (входящие)
Gmail API: письма за 24ч → эвристический префильтр (домены hh.ru/getmatch/habr/linkedin.com, ключевые слова) → Flash-Lite: классификация «про работу?» + summary ≤2 строк → секция «Почта» в дайджесте; уведомления LinkedIn (инвайты/сообщения) — отдельная секция.
Eval: `mail_classify` ≥40 писем — accuracy ≥0.9, ноль пропусков писем с офферами/интервью.
✅ Дайджест содержит секции «Почта» и «LinkedIn» с работающими ссылками; тела писем не логируются.
🖐 Сверка summary с оригиналами за 2 дня.

### Этап 3. Работа с LinkedIn (полуавтомат)
Еженедельно: заготовки инвайтов для CTO/CPO/HRBP/Senior IT Recruiter по конфиг-списку компаний — people-search URL + персонализированный текст ≤300 знаков; статусы proposed→sent→accepted кнопками; напоминание о неотправленных. Автоматизации отправки/чтения нет (grep-тест на отсутствие HTTP к linkedin.com).
Eval: `invite_rubric` — LLM-as-judge (персонализация, длина, роль, без штампов) pass ≥0.9.
✅ Понедельник → пакет заготовок; статусы обновляются.
🖐 Проверка 5 заготовок, ручная отправка первой партии.

### Этап 4. Работа с GetMatch
Контейнер userbot (второй аккаунт): чтение карточек бота GetMatch → общий пайплайн скоринга и дайджеста; ежедневное «поднятие»; непарсенное — raw-секцией.
Eval: `getmatch_parse` на корпусе реальных сообщений — accuracy ≥95%.
✅ Вакансии GetMatch в дайджесте со скорингом; деградация в raw без падения.
🖐 2 дня canary → подтверждение.

### Этап 5. Работа со скрейперами (7 сайтов)
Адаптеры VacancySourcePort: сначала исследовать JSON-эндпоинты карьерных порталов, Playwright — где иначе никак; фильтр EM-ключей на стороне адаптера; 1 rps, честный User-Agent, robots.txt; изоляция падений (метрика scraper_failures{site}); golden-тесты.
Eval: `sites_parse` per-site — field completeness; golden-diff как регресс-сигнал.
✅ Golden зелёные; вакансии сайтов в дайджесте с пометкой источника.
🖐 3-дневный canary на сайт → `/approve_scraper <site>`.

### Этап 6. CRM, хранилище, письма, MCP (финальная фича)
Полное хранилище `vacancy` (миграция: seen/labeled поверх него); агрегат Application: 💾 Сохранить, `/saved`, статусы+раунды+этапы отказа, 🗑, «➕ собес» (извлечение даты/ссылки из пересланного HR-сообщения — статус не меняет); `/stats`, `/costs`, `/review` (agreement rate); семантический few-shot selector (pgvector) + сравнительный eval против «последних N»; сопроводительные письма (Pro, русский, только факты из резюме, 🔁/✏️, отправка вручную); MCP-сервер по §4.
Eval: property-тесты статусной машины; `hr_extract` ≥0.9; `cover_letter` — hallucinations=0 (блокер) + рубрика; сравнение селекторов.
✅ Полный цикл вакансии через бот; `/costs` = Langfuse ±5%; MCP-инструменты работают из Claude Desktop через туннель.
🖐 Первый `/review` (базовый agreement rate), 5 писем на проверку фактов, диалоговый запрос через MCP.

### Этап 7. Прод-закалка
systemd, healthchecks, README (деплой, восстановление, ротация секретов, OAuth-флоу), deploy.yml проверен end-to-end, smoke на VPS.
✅ Перезагрузка VPS → всё само. 🖐 Деплой по README с нуля + restore из бэкапа.

## 7. Правила

1. Spec-kit: каждый этап → `specs/NNN-<name>/` (spec, plan, tasks) до кода; constitution — высший приоритет.
2. TDD и слои — AGENT_GUIDE.md; кейсы — TEST_CASES.md. Сначала тест.
3. Внешние вызовы — retry/backoff/таймауты; время: планировщик Europe/Moscow, БД UTC.
4. Не изобретай данных: токены, resume_id, эндпоинты — у пользователя или через CLI-хелперы.
5. Смена модели/провайдера — только конфиг + полный eval; прайсы токенов — из конфига.
6. После этапа — отчёт: сделано / acceptance / eval / что нужно для ручной проверки.
