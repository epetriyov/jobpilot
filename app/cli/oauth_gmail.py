"""CLI-хелпер OAuth Gmail (T211, quickstart этапа 2 — запускает владелец).

    uv run python -m app.cli.oauth_gmail

Поднимает локальный приёмник redirect'а (loopback, требование Google для
Desktop-клиентов), открывает авторизацию в браузере, меняет код на refresh token
и печатает строку для .env. Токены нигде не сохраняются, кроме вывода в терминал.

Напоминание: приложение в статусе Testing → refresh token живёт ~7 дней,
после протухания просто перезапустите хелпер.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from app.adapters.gmail.auth import build_authorize_url, exchange_code
from app.cli._env import ask

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/"


async def _wait_for_code() -> str:
    """Мини-HTTP-сервер: ловит один redirect с ?code=... и закрывается."""
    code_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = (await reader.readline()).decode()
        path = request_line.split(" ")[1] if " " in request_line else "/"
        params = parse_qs(urlparse(path).query)
        body = "<h3>Готово — вернитесь в терминал jobpilot.</h3>"
        writer.write(
            f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{body}".encode()
        )
        await writer.drain()
        writer.close()
        if "code" in params and not code_future.done():
            code_future.set_result(params["code"][0])

    server = await asyncio.start_server(handler, "127.0.0.1", REDIRECT_PORT)
    async with server:
        return await code_future


async def main() -> None:
    print("=== JobPilot: настройка доступа к Gmail (scope: только чтение) ===\n")
    client_id = ask("GMAIL_CLIENT_ID", "GMAIL_CLIENT_ID")
    client_secret = ask("GMAIL_CLIENT_SECRET", "GMAIL_CLIENT_SECRET")

    url = build_authorize_url(client_id=client_id, redirect_uri=REDIRECT_URI)
    print("\n1) Откройте в браузере (аккаунт из Test users!):")
    print(f"   {url}")
    print("2) Подтвердите доступ — браузер вернётся на localhost, код поймаем сами.\n")
    print("Жду redirect...")

    code = await _wait_for_code()
    tokens = await exchange_code(
        client_id=client_id, client_secret=client_secret, code=code, redirect_uri=REDIRECT_URI
    )

    print("\n✅ Готово. Добавьте в .env (показано только здесь):")
    print(f"GMAIL_REFRESH_TOKEN={tokens.refresh_token}")
    print("\nПосле этого GMAIL_MODE=auto сам переключится на реальный Gmail.")


if __name__ == "__main__":
    asyncio.run(main())
