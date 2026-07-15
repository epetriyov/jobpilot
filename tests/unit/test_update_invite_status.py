"""[N-U1] UpdateInviteStatus: переходы кнопками, недопустимый — состояние неизменно."""

from app.application.update_invite_status import UpdateInviteStatus
from app.domain.networking import InviteDraft, InviteStatus


class RepoFake:
    def __init__(self, items: dict[int, InviteDraft]) -> None:
        self.items = items

    async def get(self, invite_id: int) -> InviteDraft | None:
        return self.items.get(invite_id)

    async def save(self, invite_id: int, draft: InviteDraft) -> None:
        self.items[invite_id] = draft


def draft(status: InviteStatus = InviteStatus.PROPOSED) -> InviteDraft:
    return InviteDraft(
        title="CTO", company="Ромашка", search_url="u", invite_text="т", status=status
    )


async def test_proposed_to_sent_sets_timestamp() -> None:
    repo = RepoFake({1: draft()})
    outcome = await UpdateInviteStatus(repo=repo).run(1, InviteStatus.SENT)

    assert outcome == "ok"
    assert repo.items[1].status is InviteStatus.SENT
    assert repo.items[1].sent_at is not None


async def test_sent_to_accepted() -> None:
    repo = RepoFake({1: draft(InviteStatus.SENT)})
    assert await UpdateInviteStatus(repo=repo).run(1, InviteStatus.ACCEPTED) == "ok"
    assert repo.items[1].status is InviteStatus.ACCEPTED


async def test_illegal_transition_keeps_state() -> None:
    repo = RepoFake({1: draft(InviteStatus.ACCEPTED)})
    outcome = await UpdateInviteStatus(repo=repo).run(1, InviteStatus.SENT)

    assert outcome == "illegal"
    assert repo.items[1].status is InviteStatus.ACCEPTED  # [N-U1]: неизменно


async def test_unknown_id() -> None:
    repo = RepoFake({})
    assert await UpdateInviteStatus(repo=repo).run(404, InviteStatus.SENT) == "not_found"
