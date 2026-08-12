"""Регресс [C-U4]: карточка дайджеста несёт `vacancy_id` → кнопка 💾 Сохранить.

После ручной интеграции 6A `_select_cards` перестал проставлять id строки `vacancy`,
и клавиатура карточки скрывала 💾 (cards.py: показывает только при vacancy_id != None).
Тест фиксирует проброс id из ScoredCandidate в DigestCard.
"""

from __future__ import annotations

from app.application.run_daily_digest import RunDailyDigest
from app.domain.relevance.label import VacancySnapshot
from app.domain.relevance.score import Score
from app.domain.shared import Source, SourceRef
from app.ports.repositories import ScoredCandidate


class FakeScoring:
    def __init__(self, candidates: list[ScoredCandidate]) -> None:
        self._candidates = candidates

    async def unsent_scored(self) -> list[ScoredCandidate]:
        return self._candidates


def _candidate(external_id: str, vacancy_id: int) -> ScoredCandidate:
    ref = SourceRef(source=Source.HH, external_id=external_id)
    return ScoredCandidate(
        vacancy_id=vacancy_id,
        snapshot=VacancySnapshot(
            source_ref=ref,
            title="Engineering Manager",
            company="Acme",
            url="https://example/1",
            description_text="…",
        ),
        score=Score(value=80, reason="матч", prompt_version="v1", model="m"),
        salary_text=None,
    )


def _digest(seen: FakeScoring) -> RunDailyDigest:
    return RunDailyDigest(
        sources=[],
        seen_repo=seen,  # type: ignore[arg-type]
        scorer=object(),  # type: ignore[arg-type]
        notifier=object(),  # type: ignore[arg-type]
        dry_run=False,
        threshold=60,
        max_items=50,
    )


async def test_select_cards_propagates_vacancy_id() -> None:
    digest = _digest(FakeScoring([_candidate("1", 42)]))

    cards = await digest._select_cards()

    assert len(cards) == 1
    assert cards[0].vacancy_id == 42
