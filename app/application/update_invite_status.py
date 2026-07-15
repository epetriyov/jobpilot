"""Use case UpdateInviteStatus (спека 003, US2): кнопка → transition (N3) → persist."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol

import structlog

from app.domain.networking import IllegalTransition, InviteDraft, InviteStatus
from app.obs.metrics import invite_drafts_total

log = structlog.get_logger("application.update_invite_status")

Outcome = Literal["ok", "illegal", "not_found"]


class _RepoPort(Protocol):
    async def get(self, invite_id: int) -> InviteDraft | None: ...

    async def save(self, invite_id: int, draft: InviteDraft) -> None: ...


class UpdateInviteStatus:
    def __init__(self, *, repo: _RepoPort) -> None:
        self._repo = repo

    async def run(self, invite_id: int, to: InviteStatus) -> Outcome:
        draft = await self._repo.get(invite_id)
        if draft is None:
            return "not_found"
        try:
            draft.transition(to, at=datetime.now(UTC))
        except IllegalTransition:
            # [N-U1]: состояние неизменно, наружу — вежливый отказ
            return "illegal"
        await self._repo.save(invite_id, draft)
        invite_drafts_total.add(1, {"status": str(to)})
        log.info("invite_status_changed", invite_id=invite_id, to=str(to))
        return "ok"
