# Contract: новые переменные окружения (Этап 1)

Дополнение к contracts/env.md этапа 0; ведутся в локальном `.env` владельца.

> Пересмотр 2026-07-15: API HH недоступен. Доступ — userbot HH-бота (Telethon) + web-скрейпер (Playwright). Переменные `HH_CLIENT_*`/`HH_REFRESH_TOKEN`/`HH_RESUME_ID`/`HH_SEARCH_*` отменены.
>
> **Пересмотр 2026-07-17: email — основной источник.** userbot заблокирован (my.telegram.org отдаёт ERROR при создании api_id), web-скрейп упирается в анти-бот/VPN-блок. HH сам шлёт подборки «Вакансии по подписке» на почту, а Gmail подключён (этап 2) — их и парсим. Дефолт `HH_SOURCES=email`; доступ = наличие Gmail-refresh-token (переменные `GMAIL_*`, см. contracts этапа 2). userbot и web остаются опциональными хвостами (если каналы разблокируются).

## Режимы

| Переменная | Дефолт | Назначение |
|---|---|---|
| `HH_MODE` | `auto` | `fake` — мок-источник; `real` — email/userbot/web; `auto` — real при наличии доступа (Gmail-токен для email, userbot api_id, resume_url или залогиненный web-профиль), иначе fake |
| `HH_SOURCES` | `email` | какие адаптеры активны в real-режиме (через запятую: `email`,`telegram`,`web`) |
| `HH_EMAIL_SINCE_HOURS` | `48` | окно выборки писем HH из Gmail |
| `LLM_MODE` | `auto` | `fake` — стаб-скоринг (llm_call пишется); `real` — LLM из конфига; `auto` — real при наличии ключа |

## Доступ к источникам (real-режим; заводит владелец хелперами)

Основной источник — **email** (`HH_SOURCES=email`): отдельных HH-переменных не нужно, письма берутся через уже настроенный Gmail (`GMAIL_CLIENT_ID`/`GMAIL_CLIENT_SECRET`/`GMAIL_REFRESH_TOKEN`, contracts этапа 2). Ниже — переменные опциональных хвостов userbot/web:

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

`HH_USERBOT_API_HASH` — в `Settings.secret_values()` → маскируется в логах ([X-U1]). Session-файл userbot и браузер-профиль — секреты, в git не попадают (`deploy/userbot/`, `deploy/hh_profile/` под .gitignore). Docker-образ с Chromium (`--build-arg INSTALL_BROWSERS=true`) нужен только для web-хвоста; при основном email-источнике браузер не требуется.
