"""[T507][US3] RunDailyDigest._send: основной поток + секция «На проверку (canary)».

Одобренные/не-сайтовые карточки → основной раздел; неодобренные canary-сайты →
отдельный раздел с пометкой `site:<name> · canary`; все отмечаются digest_sent.
Фейки вместо БД/скоринга — фокус на сборке разделов.
"""

from __future__ import annotations

from datetime import datetime

from app.application.run_daily_digest import RunDailyDigest
from app.domain.shared import SourceRef
from app.ports.notifier import DigestCard


def card(ref_key: str) -> DigestCard:
    return DigestCard(
        ref_key=ref_key,
        title="Engineering Manager",
        company="Acme",
        url="https://example/1",
        salary_text=None,
        score=80,
        reason="матч",
    )


class SpyNotifier:
    def __init__(self) -> None:
        self.digests: list[str] = []
        self.cards: list[DigestCard] = []

    async def send_digest(self, text: str) -> None:
        self.digests.append(text)

    async def send_message(self, text: str) -> None: ...

    async def send_card(self, card: DigestCard) -> None:
        self.cards.append(card)

    async def send_invite_card(self, card: DigestCard) -> None: ...


class FakeSeen:
    def __init__(self) -> None:
        self.sent: list[SourceRef] = []

    async def mark_digest_sent(self, refs, at: datetime) -> None:  # type: ignore[no-untyped-def]
        self.sent.extend(refs)


class FakeApproval:
    def __init__(self, approved: set[str]) -> None:
        self._approved = approved

    async def approved_sites(self) -> set[str]:
        return self._approved


def make_digest(notifier: SpyNotifier, seen: FakeSeen, approval: FakeApproval) -> RunDailyDigest:
    return RunDailyDigest(
        sources=[],
        seen_repo=seen,  # type: ignore[arg-type]
        scorer=object(),  # type: ignore[arg-type]
        notifier=notifier,  # type: ignore[arg-type]
        dry_run=False,
        threshold=60,
        max_items=50,
        canary_sites={"yandex"},
        approval=approval,  # type: ignore[arg-type]
    )


async def test_canary_section_separated() -> None:
    notifier, seen = SpyNotifier(), FakeSeen()
    digest = make_digest(notifier, seen, FakeApproval(approved=set()))

    await digest._send([card("hh:1"), card("site:yandex:2")])

    headers = "\n".join(notifier.digests)
    assert "На проверку (canary)" in headers
    # обе карточки отмечены отправленными (не повторятся)
    assert {r.as_key() for r in seen.sent} == {"hh:1", "site:yandex:2"}
    notes = {c.ref_key: c.note for c in notifier.cards}
    assert notes["hh:1"] is None
    assert notes["site:yandex:2"] == "site:yandex · canary"


async def test_approved_site_no_canary_section() -> None:
    notifier, seen = SpyNotifier(), FakeSeen()
    digest = make_digest(notifier, seen, FakeApproval(approved={"yandex"}))

    await digest._send([card("site:yandex:2")])

    assert all("canary" not in d for d in notifier.digests)
    assert notifier.cards[0].note == "site:yandex"
