# Contract: новые переменные окружения (Этап 1)

Дополнение к contracts/env.md этапа 0; ведутся в локальном `.env` владельца.

## Обязательные для HH (без них HH-функции не активируются, сервис стартует)

| Переменная | Назначение | Откуда |
|---|---|---|
| `HH_CLIENT_ID` | id приложения HH API | dev.hh.ru, регистрирует владелец |
| `HH_CLIENT_SECRET` | secret приложения (SecretStr) | там же |
| `HH_REFRESH_TOKEN` | долгоживущий токен владельца (SecretStr) | CLI-хелпер `python -m app.cli.oauth_hh` |
| `HH_RESUME_ID` | id резюме EM для поднятия | хелпер показывает список |

## Режимы (моки до кредов — решение владельца, 2026-07-13)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `HH_MODE` | `auto` | `fake` — мок-источник HH (реалистичный пул вакансий, новые на каждый fetch); `real` — реальный API; `auto` — real при наличии `HH_REFRESH_TOKEN`, иначе fake |
| `LLM_MODE` | `auto` | `fake` — детерминированный стаб-скоринг (без внешних вызовов, llm_call пишется); `real` — LLM из конфига; `auto` — real при наличии ключа |

Переключение mocks → реальный HH: заполнить `HH_*`-креды (хелпер oauth_hh) — `auto` сам перейдёт на real; либо явно `HH_MODE=real`.

## Опциональные (дефолты)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `HH_USER_AGENT` | `JobPilot/0.1 (jobpilot-owner)` | обязательный заголовок HH-User-Agent (HH требует контакт — владелец подставляет email) |
| `HH_SEARCH_QUERIES` | `Engineering Manager;Head of Engineering;Руководитель разработки` | список запросов через `;` |
| `HH_SEARCH_PAGES` | `2` | страниц пагинации на запрос |
| `HH_REQUEST_PAUSE_SEC` | `0.5` | пауза между запросами |
| `DIGEST_CRON` | `0 10 * * *` (Europe/Moscow) | расписание дайджеста |
| `PUBLISH_INTERVAL_HOURS` | `4` | слот поднятия |
| `FEWSHOT_LIMIT` | `10` | размер few-shot (R3) |
| `FEWSHOT_TEXT_LIMIT` | `800` | усечение текста примера |

Секреты `HH_CLIENT_SECRET`, `HH_REFRESH_TOKEN` добавляются в `Settings.secret_values()` → санитайзер логов маскирует их автоматически ([X-U1]).
