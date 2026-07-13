"""OwnerOnlyMiddleware: бот отвечает только владельцу ([F-U2], constitution IV/VI)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger("bot.middleware")

Handler = Callable[[Any, dict[str, Any]], Awaitable[Any]]


class OwnerOnlyMiddleware:
    """Пропускает апдейты только от OWNER_CHAT_ID; чужие — молчаливый игнор + warning.

    Message несёт chat.id; CallbackQuery — только from_user.id (этап 1, кнопки 👍/👎).
    """

    def __init__(self, owner_chat_id: int) -> None:
        self._owner = owner_chat_id

    async def __call__(self, handler: Handler, event: Any, data: dict[str, Any]) -> Any:
        chat = getattr(event, "chat", None)
        sender_id = getattr(chat, "id", None)
        if sender_id is None:
            user = getattr(event, "from_user", None)
            sender_id = getattr(user, "id", None)
        if sender_id != self._owner:
            log.warning("foreign_chat_ignored", chat_id=sender_id)
            return None
        return await handler(event, data)
