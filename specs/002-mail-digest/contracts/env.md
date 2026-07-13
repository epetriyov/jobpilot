# Contract: переменные окружения (Этап 2)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `GMAIL_MODE` | `auto` | fake — мок-корпус писем; real — Gmail API; auto — real при наличии refresh token |
| `GMAIL_CLIENT_ID` | — | OAuth-приложение Google Cloud (заводит владелец) |
| `GMAIL_CLIENT_SECRET` | — | SecretStr, в санитайзер |
| `GMAIL_REFRESH_TOKEN` | — | SecretStr, из `python -m app.cli.oauth_gmail` |
| `MAIL_WHITELIST_DOMAINS` | `hh.ru;getmatch.ru;habr.com;linkedin.com` | префильтр M1 |
| `MAIL_BODY_LIMIT` | `2000` | усечение текста письма для LLM |
| `LLM_MODEL_SUMMARY` | (этап 0) | модель классификации/summary |

Секреты Gmail добавляются в `Settings.secret_values()` → маскирование в логах ([X-U1]).
