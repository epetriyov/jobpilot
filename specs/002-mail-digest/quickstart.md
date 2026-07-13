# Quickstart: проверка этапа 2 руками

## Мок-режим (сразу, без кредов)

```bash
make lint && make test && make migrate      # 0003_stage2 применена
docker compose up -d --build
# Telegram (dev-бот): /digest
```
Ожидаемо: помимо карточек вакансий — секция «📬 Почта» (2–4 письма с summary ≤2 строк и ссылками; рассылка магазина НЕ показана) и секция «💼 LinkedIn» («X wants to connect»). Повторный /digest не дублирует старые письма; свежие мок-письма появляются.

Проверка приватности: `docker compose logs bot worker | grep -i "текст мок-письма"` — пусто ([M-C2]).

## Подключение реального Gmail (когда будут креды)

1. Google Cloud Console → проект → OAuth client (Desktop) → `GMAIL_CLIENT_ID/SECRET` в `.env`.
2. `uv run python -m app.cli.oauth_gmail` → браузер → refresh token → в `.env`.
3. `GMAIL_MODE` не трогать (auto сам перейдёт на real) → перезапуск compose.

## Eval

```bash
make eval CONTEXT=mail_classify   # accuracy ≥0.9; пропуски offer/interview = 0 (блокер)
```

## Закрытие этапа (🖐 владелец)

2 дня сверки summary с оригиналами писем → подтверждение → этап закрыт (вместе с хвостом этапа 1 при появлении кредов HH).
