"""Домен NETWORKING (DOMAIN.md §3.5): статусная машина N3, схема текста N2, пары/URL.

Кейсы: [N-U1] переходы только вперёд; [N-U2] текст ≤300 по схеме; [N-C1]-домен.
"""

import pytest
from pydantic import ValidationError

from app.domain.networking import (
    IllegalTransition,
    InviteDraft,
    InviteStatus,
    InviteText,
    build_pairs,
    people_search_url,
)


def draft(status: InviteStatus = InviteStatus.PROPOSED) -> InviteDraft:
    return InviteDraft(
        title="CTO",
        company="Ромашка",
        search_url=people_search_url(role="CTO", company="Ромашка"),
        invite_text="Здравствуйте! Слежу за Ромашкой, буду рад связаться.",
        status=status,
    )


class TestTransitionsNU1:
    """[N-U1] proposed→sent→accepted; назад/через ступень — IllegalTransition (N3)."""

    def test_forward_path(self) -> None:
        d = draft()
        d.transition(InviteStatus.SENT)
        assert d.status is InviteStatus.SENT
        d.transition(InviteStatus.ACCEPTED)
        assert d.status is InviteStatus.ACCEPTED

    def test_accepted_to_sent_rejected(self) -> None:
        d = draft(InviteStatus.ACCEPTED)
        with pytest.raises(IllegalTransition):
            d.transition(InviteStatus.SENT)
        assert d.status is InviteStatus.ACCEPTED  # состояние неизменно

    def test_skip_step_rejected(self) -> None:
        d = draft()
        with pytest.raises(IllegalTransition):
            d.transition(InviteStatus.ACCEPTED)  # мимо sent
        assert d.status is InviteStatus.PROPOSED

    def test_all_backward_pairs_rejected(self) -> None:
        order = [InviteStatus.PROPOSED, InviteStatus.SENT, InviteStatus.ACCEPTED]
        for i, frm in enumerate(order):
            for to in order[: i + 1]:  # назад и в себя
                d = draft(frm)
                with pytest.raises(IllegalTransition):
                    d.transition(to)


class TestInviteTextNU2:
    """[N-U2] Текст 400 знаков → реджект схемой (retry — забота адаптера LLM)."""

    def test_300_ok(self) -> None:
        assert InviteText(text="х" * 300).text

    def test_301_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InviteText(text="х" * 301)


class TestPairsAndUrlNC1:
    def test_cartesian_minus_active(self) -> None:
        pairs = build_pairs(
            companies=["Ромашка", "Финтех"],
            roles=["CTO", "HRBP"],
            active={("Ромашка", "CTO")},
        )
        assert ("Ромашка", "CTO") not in pairs
        assert len(pairs) == 3  # 2×2 − 1

    def test_five_by_four_gives_twenty(self) -> None:
        pairs = build_pairs(
            companies=[f"C{i}" for i in range(5)],
            roles=["CTO", "CPO", "HRBP", "Senior IT Recruiter"],
            active=set(),
        )
        assert len(pairs) == 20  # [N-C1]

    def test_url_encodes_cyrillic_and_spaces(self) -> None:
        url = people_search_url(role="Senior IT Recruiter", company="Яндекс")
        assert url.startswith("https://www.linkedin.com/search/results/people/?keywords=")
        assert " " not in url
        assert "%D0%AF%D0%BD%D0%B4%D0%B5%D0%BA%D1%81" in url  # «Яндекс»
        assert "Senior%20IT%20Recruiter" in url
