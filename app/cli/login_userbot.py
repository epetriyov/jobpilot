"""CLI-хелпер входа userbot (Telethon, второй аккаунт) — запускает владелец один раз.

    uv run python -m app.cli.login_userbot

Создаёт session-файл: интерактивный вход по номеру телефона + код из Telegram
(при 2FA — пароль). Session переиспользуется userbot'ом для чтения HH-бота
(и GetMatch на этапе 4). Значения api_hash/кода не логируются.
"""

from __future__ import annotations

import asyncio

from telethon import TelegramClient

from app.cli._env import ask, read_env_var


async def main() -> None:
    print("=== JobPilot: вход userbot (Telethon, второй аккаунт) ===\n")
    api_id = int(ask("HH_USERBOT_API_ID (my.telegram.org)", "HH_USERBOT_API_ID"))
    api_hash = ask("HH_USERBOT_API_HASH", "HH_USERBOT_API_HASH")
    session_path = read_env_var("HH_USERBOT_SESSION") or "deploy/userbot/hh.session"

    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()  # интерактивно спросит телефон, код, 2FA-пароль
    me = await client.get_me()
    username = getattr(me, "username", None) or getattr(me, "first_name", "?")
    await client.disconnect()

    print(f"\n✅ Session сохранён: {session_path} (аккаунт: {username})")
    print("Убедитесь, что этот аккаунт подписан на HH-бота (HH_BOT_USERNAME).")


if __name__ == "__main__":
    asyncio.run(main())
