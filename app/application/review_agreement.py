"""Use case ReviewAgreement (спека 006, US4, [C-E2], T6C-3): agreement rate.

`/review`: N случайных скоренных вакансий → вердикт модели (score vs порог) сверяется
с вердиктом владельца 👍/👎. Совпадение — согласие; расхождение → вердикт владельца
(истина) дописывается в `label` через LabelRepository.upsert. Метрика — доля согласий.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, ConfigDict

from app.domain.relevance import LabeledVacancy, Verdict
from app.domain.shared import SourceRef
from app.ports.repositories import LabelRepositoryPort, VacancyStatsReaderPort

log = structlog.get_logger("application.review_agreement")


def _model_verdict(score: int | None, threshold: int) -> Verdict:
    """Вердикт модели из скора: score >= порог → relevant (порог включительно)."""
    return "relevant" if (score or 0) >= threshold else "irrelevant"


class ReviewCandidate(BaseModel):
    """Скоренная вакансия на ревью: снапшот + вердикт модели (для сверки с владельцем)."""

    model_config = ConfigDict(frozen=True)

    source_ref: SourceRef
    title: str
    company: str
    url: str
    description_text: str
    score: int
    model_verdict: Verdict


class RecordedVerdict(BaseModel):
    """Итог одной сверки: совпал ли вердикт владельца со скором; записан ли label."""

    model_config = ConfigDict(frozen=True)

    source_ref: SourceRef
    owner_verdict: Verdict
    model_verdict: Verdict
    agreed: bool
    recorded_label: bool


class ReviewSummary(BaseModel):
    """Сводка ревью: доля согласий владельца со скором модели."""

    model_config = ConfigDict(frozen=True)

    total: int
    agreed: int
    disagreed: int
    agreement_rate: float

    @classmethod
    def of(cls, agreed: int, total: int) -> ReviewSummary:
        return cls(
            total=total,
            agreed=agreed,
            disagreed=total - agreed,
            agreement_rate=(agreed / total if total else 0.0),
        )


class ReviewAgreement:
    def __init__(
        self,
        *,
        vacancies: VacancyStatsReaderPort,
        labels: LabelRepositoryPort,
        threshold: int,
    ) -> None:
        self._vacancies = vacancies
        self._labels = labels
        self._threshold = threshold

    async def sample(self, n: int) -> list[ReviewCandidate]:
        rows = await self._vacancies.random_scored(n)
        return [
            ReviewCandidate(
                source_ref=row.source_ref,
                title=row.title,
                company=row.company,
                url=row.url,
                description_text=row.description_text,
                score=row.score or 0,
                model_verdict=_model_verdict(row.score, self._threshold),
            )
            for row in rows
        ]

    async def record(self, candidate: ReviewCandidate, owner_verdict: Verdict) -> RecordedVerdict:
        agreed = candidate.model_verdict == owner_verdict
        recorded_label = False
        if not agreed:
            # вердикт владельца — истина: пишем расхождение в разметку (топливо few-shot)
            await self._labels.upsert(
                LabeledVacancy(
                    source_ref=candidate.source_ref,
                    title=candidate.title,
                    company=candidate.company,
                    url=candidate.url,
                    description_text=candidate.description_text,
                    verdict=owner_verdict,
                )
            )
            recorded_label = True
            log.info(
                "review_disagreement",
                source_ref=candidate.source_ref.as_key(),
                owner=owner_verdict,
                model=candidate.model_verdict,
            )
        return RecordedVerdict(
            source_ref=candidate.source_ref,
            owner_verdict=owner_verdict,
            model_verdict=candidate.model_verdict,
            agreed=agreed,
            recorded_label=recorded_label,
        )
