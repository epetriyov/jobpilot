"""Contract-тест ReviewAgreement (спека 006, US4, [C-E2], T6C-3): agreement rate.

`/review`: N случайных скоренных вакансий → вердикт модели (score vs порог) сверяется
с вердиктом владельца. Совпадение — согласие; расхождение → вердикт владельца
дописывается в `label` (LabelRepository.upsert). Логика — чистая (fake-репозитории).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.review_agreement import (
    RecordedVerdict,
    ReviewAgreement,
    ReviewCandidate,
    ReviewSummary,
)
from app.domain.relevance import LabeledVacancy
from app.domain.shared import Source, SourceRef
from app.ports.repositories import VacancyCounts, VacancyRecord


def _record(vacancy_id: int, score: int) -> VacancyRecord:
    return VacancyRecord(
        id=vacancy_id,
        source_ref=SourceRef(source=Source.HH, external_id=str(vacancy_id)),
        title=f"EM {vacancy_id}",
        company="Acme",
        url=f"https://hh.ru/{vacancy_id}",
        description_text="описание",
        score=score,
        first_seen_at=datetime.now(UTC),
    )


class FakeVacancyStats:
    def __init__(self, scored: list[VacancyRecord]) -> None:
        self._scored = scored

    async def counts(self) -> VacancyCounts:  # pragma: no cover
        return VacancyCounts(total=len(self._scored), scored=len(self._scored))

    async def random_scored(self, limit: int) -> list[VacancyRecord]:
        return self._scored[:limit]


class FakeLabelRepo:
    def __init__(self) -> None:
        self.upserts: list[LabeledVacancy] = []

    async def upsert(self, labeled: LabeledVacancy, embedding: list[float] | None = None) -> None:
        self.upserts.append(labeled)


class TestSample:
    async def test_model_verdict_from_score_threshold(self) -> None:
        vacancies = FakeVacancyStats([_record(1, 80), _record(2, 30), _record(3, 60)])
        uc = ReviewAgreement(vacancies=vacancies, labels=FakeLabelRepo(), threshold=60)

        candidates = await uc.sample(10)

        by_id = {c.source_ref.external_id: c for c in candidates}
        assert by_id["1"].model_verdict == "relevant"  # 80 >= 60
        assert by_id["2"].model_verdict == "irrelevant"  # 30 < 60
        assert by_id["3"].model_verdict == "relevant"  # 60 >= 60 (порог включительно)

    async def test_sample_respects_n(self) -> None:
        vacancies = FakeVacancyStats([_record(i, 70) for i in range(5)])
        uc = ReviewAgreement(vacancies=vacancies, labels=FakeLabelRepo(), threshold=60)
        assert len(await uc.sample(3)) == 3


class TestRecordVerdict:
    def _candidate(self, score: int, model_verdict: str) -> ReviewCandidate:
        return ReviewCandidate(
            source_ref=SourceRef(source=Source.HH, external_id="42"),
            title="EM",
            company="Acme",
            url="https://hh.ru/42",
            description_text="описание",
            score=score,
            model_verdict=model_verdict,  # type: ignore[arg-type]
        )

    async def test_agreement_does_not_write_label(self) -> None:
        labels = FakeLabelRepo()
        uc = ReviewAgreement(vacancies=FakeVacancyStats([]), labels=labels, threshold=60)
        cand = self._candidate(80, "relevant")

        recorded = await uc.record(cand, "relevant")

        assert isinstance(recorded, RecordedVerdict)
        assert recorded.agreed is True
        assert recorded.recorded_label is False
        assert labels.upserts == []

    async def test_disagreement_writes_owner_verdict_to_label(self) -> None:
        labels = FakeLabelRepo()
        uc = ReviewAgreement(vacancies=FakeVacancyStats([]), labels=labels, threshold=60)
        cand = self._candidate(80, "relevant")  # модель: relevant

        recorded = await uc.record(cand, "irrelevant")  # владелец: irrelevant

        assert recorded.agreed is False
        assert recorded.recorded_label is True
        assert len(labels.upserts) == 1
        written = labels.upserts[0]
        assert written.verdict == "irrelevant"  # истина — вердикт владельца
        assert written.source_ref.external_id == "42"
        assert written.title == "EM"
        assert written.url == "https://hh.ru/42"


class TestReviewSummary:
    def test_agreement_rate(self) -> None:
        summary = ReviewSummary.of(agreed=7, total=10)
        assert summary.total == 10
        assert summary.agreed == 7
        assert summary.disagreed == 3
        assert summary.agreement_rate == 0.7

    def test_empty_review_zero_rate(self) -> None:
        summary = ReviewSummary.of(agreed=0, total=0)
        assert summary.agreement_rate == 0.0
