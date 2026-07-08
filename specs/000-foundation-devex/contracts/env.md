# Contract: конфигурация (env)

Источник: `.env` (никогда не коммитится) / переменные окружения. Шаблона `.env.example` в репо нет (решение владельца, 2026-07-08): `.env` ведётся владельцем локально, этот файл — единственный справочник переменных. Загрузка — `app/config.py` (pydantic-settings). Отсутствие обязательной переменной = понятная ошибка с её именем при старте ([F-U1]).

## Обязательные (сервис не стартует без них)

| Переменная | Назначение | Кто выдаёт |
|---|---|---|
| `TELEGRAM_API_TOKEN` | токен бота | пользователь (BotFather) |
| `OWNER_CHAT_ID` | chat_id владельца — единственного пользователя | пользователь |
| `OPENROUTER_API_KEY` | ключ OpenRouter (все LLM) | пользователь |
| `POSTGRES_DSN` | DSN Postgres | compose-дефолт локально; VPS — env |

## Обязательные для телеметрии в облако (без них — телеметрия только локально, сервисы работают)

| Переменная | Назначение |
|---|---|
| `GRAFANA_CLOUD_OTLP_ENDPOINT` | OTLP-endpoint стека Grafana Cloud (`https://otlp-gateway-<zone>.grafana.net/otlp`) |
| `GRAFANA_CLOUD_INSTANCE_ID` | OTLP instance id (basic-auth user) |
| `GRAFANA_CLOUD_API_TOKEN` | API-токен (basic-auth password; общий для OTLP и remote_write) |
| `GCLOUD_HOSTED_METRICS_URL` | Prometheus push-URL (`.../api/prom/push`) — метрики хоста VPS из Alloy |
| `GCLOUD_HOSTED_METRICS_ID` | Prometheus instance id (basic-auth user для remote_write) |

Эти переменные читает только контейнер alloy (`deploy/alloy/config.alloy`, настроен владельцем через мастер Grafana Cloud); приложение кредов Grafana не видит.

## Опциональные (дефолты в конфиге)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `DRY_RUN` | `true` | сухой прогон: без внешних записей, пометка «ТЕСТ» |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-совместимый endpoint |
| `LLM_MODEL_SCORING` | `google/gemini-2.5-flash-lite` | модель скоринга |
| `LLM_MODEL_SUMMARY` | `google/gemini-2.5-flash-lite` | модель summary |
| `LLM_MODEL_LETTERS` | `google/gemini-2.5-pro` | модель писем (этап 6) |
| `LLM_MODEL_JUDGE` | `google/gemini-2.5-flash` | LLM-as-judge в eval |
| `PRICE_PER_MTOK_IN` / `PRICE_PER_MTOK_OUT` | `0.10` / `0.40` | фолбэк-прайс $/1M токенов |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://alloy:4317` | локальный коллектор |
| `TZ_SCHEDULER` | `Europe/Moscow` | зона планировщика (БД — UTC) |
| `DIGEST_SCORE_THRESHOLD` | `60` | порог дайджеста (R4) |
| `DIGEST_MAX_ITEMS` | `50` | максимум карточек (R4) |

## GitHub Secrets (CI/deploy, не в .env)

| Секрет | Для чего |
|---|---|
| `ANTHROPIC_API_KEY` | claude-code-action (авторевью PR) |
| `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` | deploy.yml по тегу |

Правила: значения секретов не попадают в код/логи/промпты ([X-U1]); CI-джобы lint/test/recorded-eval выполняются вообще без секретов.
