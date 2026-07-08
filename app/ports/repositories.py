"""Repository-порты минимального слоя хранения (contracts/repositories.md)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from app.domain.relevance import LabeledVacancy
from app.domain.shared import SourceRef
from app.domain.sourcing import Vacancy

__all__ = [
    "JobRunRepositoryPort",
    "LabelRepositoryPort",
    "LabeledVacancy",
    "SeenVacancyRepositoryPort",
]


class SeenVacancyRepositoryPort(Protocol):
    async def is_seen(self, ref: SourceRef) -> bool: ...

    async def mark_seen(self, vacancy: Vacancy) -> None:
        """Идемпотентно: повторный вызов не меняет first_seen_at (S1)."""
        ...

    async def find_duplicate(self, normalized_key: str, within_days: int = 30) -> str | None:
        """source_ref-ключ оригинала для кросс-источникового дедупа (S2)."""
        ...

    async def mark_digest_sent(self, refs: Sequence[SourceRef], at: datetime) -> None: ...


class LabelRepositoryPort(Protocol):
    async def add(self, labeled: LabeledVacancy) -> None: ...

    async def recent(self, limit: int = 10) -> list[LabeledVacancy]:
        """Few-shot «последние N» (R3)."""
        ...


class JobRunRepositoryPort(Protocol):
    async def start(self, job_name: str, trace_id: str) -> int: ...

    async def finish(
        self,
        run_id: int,
        *,
        status: Literal["success", "partial", "error"],
        items_in: int = 0,
        items_out: int = 0,
        error: str | None = None,
    ) -> None: ...
