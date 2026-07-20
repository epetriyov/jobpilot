"""Агрегат InviteDraft и правила нетворкинга (DOMAIN.md §3.5: N1–N3).

N1 — полуавтомат: search_url — ссылка ДЛЯ владельца, система в LinkedIn не ходит
(гарантия — grep-тест [N-U3]). N2 — текст ≤300 знаков. N3 — статусы только вперёд.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

PEOPLE_SEARCH_BASE = "https://www.linkedin.com/search/results/people/?keywords="


class IllegalTransition(Exception):
    """Недопустимый переход статуса; состояние агрегата не меняется (ср. CRM §3.3)."""


class InviteStatus(StrEnum):
    PROPOSED = "proposed"
    SENT = "sent"
    ACCEPTED = "accepted"


_ALLOWED: dict[InviteStatus, InviteStatus] = {
    InviteStatus.PROPOSED: InviteStatus.SENT,
    InviteStatus.SENT: InviteStatus.ACCEPTED,
}


class InviteText(BaseModel):
    """Схема выхода LLM: персонализированный инвайт ≤300 знаков (N2)."""

    text: str = Field(max_length=300, min_length=1)


class InviteDraft(BaseModel):
    """Заготовка инвайта: роль + компания + ссылка + текст; ПД адресата нет (N1)."""

    model_config = ConfigDict(validate_assignment=True)

    title: str
    company: str
    search_url: str
    invite_text: str = Field(max_length=300)
    status: InviteStatus = InviteStatus.PROPOSED
    sent_at: datetime | None = None
    accepted_at: datetime | None = None

    def transition(self, to: InviteStatus, *, at: datetime | None = None) -> None:
        """N3: только proposed→sent→accepted; иначе IllegalTransition, состояние неизменно."""
        if _ALLOWED.get(self.status) is not to:
            raise IllegalTransition(f"{self.status} → {to} запрещён (N3)")
        self.status = to
        if to is InviteStatus.SENT:
            self.sent_at = at
        elif to is InviteStatus.ACCEPTED:
            self.accepted_at = at


def people_search_url(*, role: str, company: str) -> str:
    """Ссылка people-search для владельца; percent-encoding включая кириллицу ([N-C1])."""
    return PEOPLE_SEARCH_BASE + quote(f"{role} {company}")


def build_pairs(
    *,
    companies: list[str],
    roles: list[str],
    active: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Декартово произведение компании×роли минус активные (не-accepted) пары ([N-C1])."""
    return [
        (company, role) for company in companies for role in roles if (company, role) not in active
    ]
