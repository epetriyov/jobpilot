"""Use case FunnelStats (спека 006, US4, T6C-1): воронка Application + счётчики.

`/stats` = воронка заявок по статусам §3.3 (ApplicationRepository.funnel_counts) с
конверсиями переходов вперёд + счётчики хранилища `vacancy` и разметки 👍/👎.
Только чтение; конверсии считаются из терминальных статусов (переходы — только вперёд).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domain.crm import ApplicationStatus
from app.ports.repositories import (
    ApplicationRepositoryPort,
    LabelRepositoryPort,
    VacancyStatsReaderPort,
)

_ACTIVE_ORDER = (
    ApplicationStatus.NEW,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


class FunnelReport(BaseModel):
    """Отчёт /stats: воронка, конверсии, счётчики хранилища и разметки."""

    model_config = ConfigDict(frozen=True)

    counts: dict[str, int]  # все 5 статусов, 0-заполнено
    total: int
    reached_applied: int
    reached_interview: int
    reached_offer: int
    applied_rate: float  # reached_applied / total
    interview_rate: float  # reached_interview / reached_applied
    offer_rate: float  # reached_offer / reached_interview
    rejected: int
    vacancies_total: int
    vacancies_scored: int
    labeled_relevant: int
    labeled_irrelevant: int


class FunnelStats:
    def __init__(
        self,
        *,
        apps: ApplicationRepositoryPort,
        vacancies: VacancyStatsReaderPort,
        labels: LabelRepositoryPort,
    ) -> None:
        self._apps = apps
        self._vacancies = vacancies
        self._labels = labels

    async def run(self) -> FunnelReport:
        raw = await self._apps.funnel_counts()
        counts = {status.value: raw.get(status.value, 0) for status in ApplicationStatus}
        total = sum(counts.values())

        # «дошёл до этапа» = сумма текущих в этом и последующих активных статусах
        # (переходы только вперёд §3.3: offer прошёл applied+interview).
        reached_offer = counts[ApplicationStatus.OFFER.value]
        reached_interview = reached_offer + counts[ApplicationStatus.INTERVIEW.value]
        reached_applied = reached_interview + counts[ApplicationStatus.APPLIED.value]

        vacancy_counts = await self._vacancies.counts()
        relevant, irrelevant = await self._labels.counts()

        return FunnelReport(
            counts=counts,
            total=total,
            reached_applied=reached_applied,
            reached_interview=reached_interview,
            reached_offer=reached_offer,
            applied_rate=_rate(reached_applied, total),
            interview_rate=_rate(reached_interview, reached_applied),
            offer_rate=_rate(reached_offer, reached_interview),
            rejected=counts[ApplicationStatus.REJECTED.value],
            vacancies_total=vacancy_counts.total,
            vacancies_scored=vacancy_counts.scored,
            labeled_relevant=relevant,
            labeled_irrelevant=irrelevant,
        )
