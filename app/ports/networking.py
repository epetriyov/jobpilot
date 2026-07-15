"""InviteRepositoryPort — хранение заготовок инвайтов (data-model этапа 3)."""

from __future__ import annotations

from typing import Protocol

from app.domain.networking import InviteDraft


class InviteRepositoryPort(Protocol):
    async def active_pairs(self) -> set[tuple[str, str]]:
        """Пары (company, title) в статусах proposed/sent — дедуп еженедельных запусков."""
        ...

    async def add(self, draft: InviteDraft) -> int: ...

    async def get(self, invite_id: int) -> InviteDraft | None: ...

    async def save(self, invite_id: int, draft: InviteDraft) -> None: ...

    async def pending(self) -> list[tuple[int, InviteDraft]]: ...

    async def pending_older_than(self, days: int) -> list[tuple[int, InviteDraft]]: ...

    async def counts(self) -> dict[str, int]: ...
