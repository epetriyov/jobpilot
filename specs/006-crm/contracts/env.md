# Contract: переменные окружения (Этап 6)

Секреты — только из env (constitution IV); в код/логи/промпты/MCP не попадают. Новое этапа 6 по под-этапам.

## 6D — pgvector / эмбеддинги

| Переменная | Дефолт | Назначение |
|---|---|---|
| `LLM_MODEL_EMBEDDING` | `openai/text-embedding-3-small` | модель эмбеддингов (OpenRouter /embeddings поддерживает только `openai/text-embedding-*`; адаптер шлёт `dimensions=768` → 768-мерный вектор под колонку; смена размерности → ADR + миграция типа колонки) |
| `FEWSHOT_MIN_EMBEDDED` | `10` | минимум размеченных с эмбеддингами для семантического селектора; ниже — фолбэк «последние N» ([R-U2]) |
| `FEWSHOT_SELECTOR` | `semantic` | `semantic` \| `recent` — стратегия few-shot (для сравнительного eval [R-E2] и аварийного отката) |

## 6E — сопроводительные письма

| Переменная | Дефолт | Назначение |
|---|---|---|
| `LLM_MODEL_LETTERS` | `google/gemini-2.5-pro` | модель писем (уже в config.py) |
| `LLM_MODEL_JUDGE` | `google/gemini-2.5-flash` | судья для eval `cover_letter`/`invite_rubric` (уже есть) |
| `COVER_LETTER_MAX_CHARS` | `2000` | лимит письма (M3, CHECK в БД) |

## 6F — MCP-сервер

| Переменная | Дефолт | Назначение |
|---|---|---|
| `MCP_AUTH_TOKEN` | — (**секрет**, обязателен если MCP включён) | auth-токен; запрос без/с неверным → отказ (MCP3, [P-C1]) |
| `MCP_DB_DSN` | — (**секрет**) | DSN под ограниченной ролью `mcp_ro` (GRANT SELECT) для read-инструментов (MCP4, [P-I1]) |
| `MCP_TRANSPORT` | `stdio` | транспорт FastMCP; наружу порт не публикуется (localhost/SSH-туннель, research §4) |
| `MCP_ENABLED` | `false` | включение профиля `mcp` в compose |

Роль `mcp_ro` создаётся ops-скриптом деплоя (`deploy/mcp/create_ro_role.sql`), не миграцией (CREATE ROLE/GRANT — инфраструктура).

## 6A/6B/6C/6G

Новых обязательных переменных нет. `DIGEST_SCORE_THRESHOLD`/`DRY_RUN`/`TZ_SCHEDULER` — как прежде; `/costs` использует прайсы из `llm_call` (фактические из usage OpenRouter, фолбэк — `PRICE_PER_MTOK_*`). Порог `/review` — интерактивный (число вакансий передаётся командой).

## Приватность (все под-этапы)

Тела писем и HR-сообщений не логируются (M4); `cover_letter.text` — данные владельца в его БД (не лог). MCP не имеет доступа к секретам интеграций (MCP4). Все секреты этапа — в `secret_values()` санитайзера логов ([X-U1]): добавить `MCP_AUTH_TOKEN`, `MCP_DB_DSN`.
