"""NotifierPort: доставка сообщений владельцу (реализация — adapters/telegram)."""

from __future__ import annotations

from typing import Protocol


class NotifierPort(Protocol):
    async def send_digest(self, text: str) -> None: ...

    async def send_message(self, text: str) -> None: ...
