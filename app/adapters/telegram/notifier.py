"""Telegram-нотификатор (NotifierPort) поверх aiogram."""

from __future__ import annotations

from aiogram import Bot

from app.adapters.telegram.cards import (
    build_card_keyboard,
    build_invite_keyboard,
    render_card_text,
    render_invite_text,
)
from app.ports.notifier import DigestCard, InviteCard, PublishOutcome


class TelegramNotifier:
    """Отправляет дайджест/карточки/сообщения владельцу (OWNER_CHAT_ID)."""

    def __init__(self, bot: Bot, owner_chat_id: int) -> None:
        self._bot = bot
        self._owner = owner_chat_id

    async def send_digest(self, text: str) -> None:
        await self._bot.send_message(self._owner, text, disable_web_page_preview=True)

    async def send_message(self, text: str) -> None:
        await self._bot.send_message(self._owner, text)

    async def send_card(self, card: DigestCard) -> None:
        await self._bot.send_message(
            self._owner,
            render_card_text(card),
            parse_mode="HTML",
            reply_markup=build_card_keyboard(card),
            disable_web_page_preview=True,
        )

    async def send_invite_card(self, card: InviteCard) -> None:
        await self._bot.send_message(
            self._owner,
            render_invite_text(card),
            parse_mode="HTML",
            reply_markup=build_invite_keyboard(card),
            disable_web_page_preview=True,
        )


class NullPublisher:
    """Заглушка PublisherPort: рабочего канала поднятия резюме нет (web-источник HH
    выключен / нет URL). Возвращает "disabled" — НЕ ложный "published" (иначе метрика
    resume_published врёт, что резюме поднимается)."""

    async def publish(self) -> PublishOutcome:
        return "disabled"
