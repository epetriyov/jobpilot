"""Порт чтения сообщений через userbot (Telethon-реализация — в adapters)."""

from __future__ import annotations

from typing import Protocol


class TelegramMessageReaderPort(Protocol):
    """Читает последние текстовые сообщения из диалога с ботом/каналом."""

    async def recent_messages(self, peer: str, limit: int = 100) -> list[str]: ...
