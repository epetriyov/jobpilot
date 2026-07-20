"""InboxPort и репозиторий писем (DOMAIN.md §3.4, data-model этапа 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.domain.correspondence import InboxMessage


class RawEmail(BaseModel):
    """Сырое письмо из источника; body_text живёт только в памяти до промпта (M4)."""

    model_config = ConfigDict(frozen=True)

    gmail_id: str
    sender: str
    subject: str
    snippet: str
    body_text: str
    received_at: datetime
    url: str
    body_html: str = ""  # HTML-часть (для парсинга вакансий из HH-писем, этап 1-rework)


class InboxPort(Protocol):
    async def fetch_since(self, since: datetime) -> list[RawEmail]: ...


class InboxMessageRepositoryPort(Protocol):
    async def is_processed(self, gmail_id: str) -> bool: ...

    async def add(self, gmail_id: str, message: InboxMessage) -> None: ...
