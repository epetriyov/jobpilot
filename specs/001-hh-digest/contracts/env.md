# Contract: новые переменные окружения (Этап 1)

Дополнение к contracts/env.md этапа 0; ведутся в локальном `.env` владельца.

> Пересмотр 2026-07-15: API HH недоступен. Доступ — userbot HH-бота (Telethon) + web-скрейпер (Playwright). Переменные `HH_CLIENT_*`/`HH_REFRESH_TOKEN`/`HH_RESUME_ID`/`HH_SEARCH_*` отменены.

## Режимы

| Переменная | Дефолт | Назначение |
|---|---|---|
| `HH_MODE` | `auto` | `fake` — мок-источник; `real` — userbot+web; `auto` — real при наличии доступа (userbot api_id или resume_url), иначе fake |
| `HH_SOURCES` | `telegram,web` | какие адаптеры активны в real-режиме |
| `LLM_MODE` | `auto` | `fake` — стаб-скоринг (llm_call пишется); `real` — LLM из конфига; `auto` — real при наличии ключа |

## Доступ к источникам (real-режим; заводит владелец хелперами)

| Переменная | Назначение | Откуда |
|---|---|---|
| `HH_USERBOT_API_ID` | api_id Telegram-приложения | my.telegram.org |
| `HH_USERBOT_API_HASH` | api_hash (SecretStr → санитайзер) | там же |
| `HH_USERBOT_SESSION` | путь к session-файлу | `python -m app.cli.login_userbot` |
| `HH_BOT_USERNAME` | @ HH-бота в Telegram | подписка владельца |
| `HH_WEB_PROFILE_DIR` | каталог браузер-профиля (куки логина) | `python -m app.cli.hh_login` |
| `HH_RECOMMENDATIONS_URL` | URL страницы рекомендаций | конфиг |
| `HH_RESUME_URL` | URL резюме для поднятия (Playwright-клик) | владелец |

## Опциональные (дефолты)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `HH_USER_AGENT` | `JobPilot/0.1 (jobpilot-owner)` | честный User-Agent web-скрейпера |
| `HH_REQUEST_PAUSE_SEC` | `1.0` | пауза перед возвратом HTML (≥1с, [S-C10]) |
| `DIGEST_CRON` | `0 10 * * *` (Europe/Moscow) | расписание дайджеста |
| `PUBLISH_INTERVAL_HOURS` | `4` | слот поднятия |
| `FEWSHOT_LIMIT` / `FEWSHOT_TEXT_LIMIT` | `10` / `800` | few-shot (R3) |

`HH_USERBOT_API_HASH` — в `Settings.secret_values()` → маскируется в логах ([X-U1]). Session-файл userbot и браузер-профиль — секреты, в git не попадают (`deploy/userbot/`, `deploy/hh_profile/` под .gitignore). Docker-образ с Chromium собирается `--build-arg INSTALL_BROWSERS=true` (на VPS для web-источника).
