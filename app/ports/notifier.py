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
    # UI-пометка источника: `site:<name>` (+ ` · canary` в секции «На проверку»);
    # None для hh/getmatch. Заполняется на сборке дайджеста (этап 5, SC-002).
    note: str | None = None
    # id строки `vacancy` — для кнопки 💾 Сохранить (CRM, этап 6B). None до вливания 6A,
    # когда дайджест начнёт проставлять id; при None кнопка 💾 не показывается.
    vacancy_id: int | None = None


class InviteCard(BaseModel):
    """Карточка заготовки инвайта (UI, этап 3)."""

    model_config = ConfigDict(frozen=True)

    invite_id: int
    title: str
    company: str
    search_url: str
    invite_text: str
    status: str


class CoverLetterCard(BaseModel):
    """Карточка сопроводительного письма (UI, этап 6E): текст + кнопки 🔁/✏️.

    Отправку письма делает человек вручную (система не отправляет, M3/VI).
    Тело письма — данные владельца; не логируется (M4).
    """

    model_config = ConfigDict(frozen=True)

    vacancy_id: int
    title: str
    company: str
    text: str


class NotifierPort(Protocol):
    async def send_digest(self, text: str) -> None: ...

    async def send_message(self, text: str) -> None: ...

    async def send_card(self, card: DigestCard) -> None:
        """Карточка с кнопками 👍/👎/🔗 (этап 1)."""
        ...

    async def send_invite_card(self, card: InviteCard) -> None:
        """Карточка инвайта с кнопками статуса (этап 3)."""
        ...

    async def send_cover_letter_card(self, card: CoverLetterCard) -> None:
        """Карточка письма с кнопками 🔁 (перегенерировать) / ✏️ (правка) — этап 6E."""
        ...


# "disabled" — публикация недоступна (нет рабочего канала: web-источник HH выключен,
# нет URL резюме). Честный статус вместо ложного "published" у заглушки.
PublishOutcome = Literal["published", "skipped_limit", "disabled"]


class PublisherPort(Protocol):
    """Поднятие резюме (HH — этап 1). Лимит источника — штатный исход, не ошибка ([S-C3])."""

    async def publish(self) -> PublishOutcome: ...
