"""Telethon-реализация TelegramMessageReaderPort (userbot, второй аккаунт).

Тонкий I/O-слой: читает последние текстовые сообщения из диалога с ботом.
Session-файл создаётся хелпером login_userbot; сам userbot только читает.
Не покрывается CI (нужен реальный Telegram) — логика парсинга в telegram_source.
"""

from __future__ import annotations

import structlog
from telethon import TelegramClient

log = structlog.get_logger("adapters.telegram_userbot")


class TelethonReader:
    """Читает recent_messages из диалога; подключение per-fetch, session из файла."""

    def __init__(self, *, api_id: int, api_hash: str, session_path: str) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_path = session_path

    async def recent_messages(self, peer: str, limit: int = 100) -> list[str]:
        client = TelegramClient(self._session_path, self._api_id, self._api_hash)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                log.warning("userbot_not_authorized", hint="запустите app.cli.login_userbot")
                return []
            texts: list[str] = []
            async for message in client.iter_messages(peer, limit=limit):
                if message.text:
                    texts.append(message.text)
            log.info("userbot_read", peer=peer, count=len(texts))
            return texts
        finally:
            await client.disconnect()
