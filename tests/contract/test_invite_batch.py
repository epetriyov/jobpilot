"""[N-C1] BuildInviteBatch на фейках: 5×4 → ≤20, дедуп, фолбэк текста, напоминание."""

from app.adapters.llm.fake import FakeLlm, stub_invite_response
from app.application.build_invite_batch import BuildInviteBatch
from app.domain.networking import InviteDraft, InviteStatus
from app.domain.shared import PromptVersion
from app.ports.notifier import InviteCard

PV = PromptVersion(purpose="invite", version=1)
COMPANIES = ["Ромашка", "Финтех Плюс", "Яндекс", "Авито", "Озон"]
ROLES = ["CTO", "CPO", "HRBP", "Senior IT Recruiter"]


class RepoFake:
    def __init__(self) -> None:
        self.items: dict[int, InviteDraft] = {}
        self._next = 1
        self.pending_old: list[tuple[int, InviteDraft]] = []

    async def active_pairs(self) -> set[tuple[str, str]]:
        return {
            (d.company, d.title)
            for d in self.items.values()
            if d.status is not InviteStatus.ACCEPTED
        }

    async def add(self, draft: InviteDraft) -> int:
        invite_id = self._next
        self._next += 1
        self.items[invite_id] = draft
        return invite_id

    async def pending_older_than(self, days: int) -> list[tuple[int, InviteDraft]]:
        return self.pending_old


class NotifierSpy:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.cards: list[InviteCard] = []

    async def send_message(self, text: str) -> None:
        self.messages.append(text)

    async def send_invite_card(self, card: InviteCard) -> None:
        self.cards.append(card)


class _Recorder:
    async def record(self, call: object) -> None: ...


def make_use_case(
    repo: RepoFake,
    notifier: NotifierSpy,
    llm: FakeLlm,
    companies: list[str] = COMPANIES,
) -> BuildInviteBatch:
    return BuildInviteBatch(
        repo=repo,
        llm=llm,
        notifier=notifier,
        system_prompt="Сгенерируй инвайт.",
        prompt_version=PV,
        companies=companies,
        roles=ROLES,
        remind_days=3,
        dry_run=True,
    )


def stub_llm() -> FakeLlm:
    return FakeLlm(recorder=_Recorder(), response_factory=stub_invite_response)


async def test_n_c1_five_by_four_gives_twenty_cards() -> None:
    repo, notifier = RepoFake(), NotifierSpy()
    result = await make_use_case(repo, notifier, stub_llm()).run()

    assert result.created == 20
    assert len(notifier.cards) == 20
    assert len(repo.items) == 20
    card = notifier.cards[0]
    assert len(card.invite_text) <= 300
    assert card.company in card.invite_text  # персонализация: компания упомянута
    assert "linkedin.com/search/results/people" in card.search_url


async def test_dedup_against_active_pair() -> None:
    repo, notifier = RepoFake(), NotifierSpy()
    await repo.add(
        InviteDraft(
            title="CTO",
            company="Ромашка",
            search_url="u",
            invite_text="т",
            status=InviteStatus.PROPOSED,
        )
    )

    result = await make_use_case(repo, notifier, stub_llm()).run()

    assert result.created == 19  # пара (Ромашка, CTO) активна — пропущена
    assert ("Ромашка", "CTO") not in {(c.company, c.title) for c in notifier.cards}


async def test_invalid_llm_twice_falls_back_to_template() -> None:
    """[N-U2]-контракт: реджект → 1 retry → шаблон; пакет не срывается."""
    repo, notifier = RepoFake(), NotifierSpy()
    llm = FakeLlm(recorder=_Recorder(), responses=["мусор", '{"text": "' + "х" * 400 + '"}'])

    result = await make_use_case(repo, notifier, llm, companies=["Ромашка"]).run()

    assert result.created == 4  # все роли, несмотря на сбой LLM на первой
    first = notifier.cards[0]
    assert len(first.invite_text) <= 300
    assert "Ромашка" in first.invite_text  # шаблонный фолбэк тоже персонализирован


async def test_reminder_for_stale_pending() -> None:
    repo, notifier = RepoFake(), NotifierSpy()
    stale = InviteDraft(title="CTO", company="Старая", search_url="u", invite_text="т")
    repo.pending_old = [(99, stale)]

    await make_use_case(repo, notifier, stub_llm(), companies=[]).run()

    assert any("неотправленн" in m.lower() for m in notifier.messages)


async def test_empty_companies_friendly_message() -> None:
    repo, notifier = RepoFake(), NotifierSpy()
    result = await make_use_case(repo, notifier, stub_llm(), companies=[]).run()

    assert result.created == 0
    assert any("LINKEDIN_COMPANIES" in m for m in notifier.messages)
