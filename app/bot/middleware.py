"""OwnerOnlyMiddleware: бот отвечает только владельцу ([F-U2], constitution IV/VI)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger("bot.middleware")

Handler = Callable[[Any, dict[str, Any]], Awaitable[Any]]


class OwnerOnlyMiddleware:
    """Пропускает апдейты только от OWNER_CHAT_ID; чужие — молчаливый игнор + warning."""

    def __init__(self, owner_chat_id: int) -> None:
        self._owner = owner_chat_id

    async def __call__(self, handler: Handler, event: Any, data: dict[str, Any]) -> Any:
        chat = getattr(event, "chat", None)
        chat_id = getattr(chat, "id", None)
        if chat_id != self._owner:
            log.warning("foreign_chat_ignored", chat_id=chat_id)
            return None
        return await handler(event, data)
