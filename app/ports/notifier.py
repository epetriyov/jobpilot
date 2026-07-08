"""NotifierPort: доставка сообщений владельцу (реализация — adapters/telegram)."""

from __future__ import annotations

from typing import Protocol


class NotifierPort(Protocol):
    async def send_digest(self, text: str) -> None: ...

    async def send_message(self, text: str) -> None: ...


class PublisherPort(Protocol):
    """Внешняя запись (публикация резюve в HH — этап 1). На этапе 0 — заглушка для DRY_RUN."""

    async def publish(self) -> None: ...
