"""NotifierPort: доставка сообщений владельцу (реализация — adapters/telegram)."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class DigestCard(BaseModel):
    """Карточка вакансии для чата (UI-представление, DOMAIN.md §1 — не доменная сущность)."""

    model_config = ConfigDict(frozen=True)

    ref_key: str  # канонический SourceRef.as_key() — для callback_data разметки
    title: str
    company: str
    url: str
    salary_text: str | None
    score: int
    reason: str


class NotifierPort(Protocol):
    async def send_digest(self, text: str) -> None: ...

    async def send_message(self, text: str) -> None: ...

    async def send_card(self, card: DigestCard) -> None:
        """Карточка с кнопками 👍/👎/🔗 (этап 1)."""
        ...


PublishOutcome = Literal["published", "skipped_limit"]


class PublisherPort(Protocol):
    """Поднятие резюме (HH — этап 1). Лимит источника — штатный исход, не ошибка ([S-C3])."""

    async def publish(self) -> PublishOutcome: ...
