"""Telegram-нотификатор (NotifierPort) поверх aiogram."""

from __future__ import annotations

from aiogram import Bot


class TelegramNotifier:
    """Отправляет дайджест/сообщения владельцу (OWNER_CHAT_ID)."""

    def __init__(self, bot: Bot, owner_chat_id: int) -> None:
        self._bot = bot
        self._owner = owner_chat_id

    async def send_digest(self, text: str) -> None:
        await self._bot.send_message(self._owner, text, disable_web_page_preview=True)

    async def send_message(self, text: str) -> None:
        await self._bot.send_message(self._owner, text)


class NullPublisher:
    """Заглушка PublisherPort на этапе 0: реальная публикация (HH) — этап 1."""

    async def publish(self) -> None:
        return None
