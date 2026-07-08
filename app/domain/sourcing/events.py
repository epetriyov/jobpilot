"""События контекста Sourcing (DOMAIN.md §3.1)."""

from __future__ import annotations

from app.domain.shared import DomainEvent, SourceRef


class VacancyDiscovered(DomainEvent):
    """Первое появление вакансии в системе (после дедупликации)."""

    source_ref: SourceRef


class SourceFetchFailed(DomainEvent):
    """Падение адаптера-источника; сбор остальных продолжается (S4)."""

    source: str
    error: str
