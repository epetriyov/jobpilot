"""Contract-тест FunnelStats (спека 006, US4, T6C-1): воронка Application + счётчики.

`/stats` собирает: воронку по статусам заявок (ApplicationRepository.funnel_counts),
конверсии переходов вперёд и счётчики хранилища/разметки. Логика конверсий —
чистая (fake-репозитории), без БД.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.application.funnel_stats import FunnelReport, FunnelStats
from app.ports.repositories import VacancyCounts, VacancyRecord


class FakeAppRepo:
    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    async def funnel_counts(self) -> dict[str, int]:
        return dict(self._counts)


class FakeVacancyStats:
    def __init__(self, total: int, scored: int) -> None:
        self._counts = VacancyCounts(total=total, scored=scored)

    async def counts(self) -> VacancyCounts:
        return self._counts

    async def random_scored(self, limit: int) -> Sequence[VacancyRecord]:  # pragma: no cover
        return []


class FakeLabelRepo:
    def __init__(self, relevant: int, irrelevant: int) -> None:
        self._pair = (relevant, irrelevant)

    async def counts(self) -> tuple[int, int]:
        return self._pair


def _stats(counts: dict[str, int]) -> FunnelStats:
    return FunnelStats(
        apps=FakeAppRepo(counts),
        vacancies=FakeVacancyStats(total=100, scored=40),
        labels=FakeLabelRepo(relevant=12, irrelevant=8),
    )


class TestFunnelStats:
    async def test_counts_zero_filled_for_all_statuses(self) -> None:
        report = await _stats({"new": 2}).run()
        assert isinstance(report, FunnelReport)
        assert report.counts == {
            "new": 2,
            "applied": 0,
            "interview": 0,
            "offer": 0,
            "rejected": 0,
        }
        assert report.total == 2

    async def test_forward_conversions(self) -> None:
        report = await _stats(
            {"new": 2, "applied": 3, "interview": 4, "offer": 1, "rejected": 2}
        ).run()

        assert report.total == 12
        # «дошёл до этапа» = текущие в этом и последующих активных статусах
        assert report.reached_applied == 3 + 4 + 1
        assert report.reached_interview == 4 + 1
        assert report.reached_offer == 1
        assert report.rejected == 2
        assert report.applied_rate == 8 / 12
        assert report.interview_rate == 5 / 8
        assert report.offer_rate == 1 / 5

    async def test_rates_guard_zero_division(self) -> None:
        report = await _stats({}).run()
        assert report.total == 0
        assert report.applied_rate == 0.0
        assert report.interview_rate == 0.0
        assert report.offer_rate == 0.0

    async def test_store_and_label_counters_passthrough(self) -> None:
        report = await _stats({"new": 1}).run()
        assert report.vacancies_total == 100
        assert report.vacancies_scored == 40
        assert report.labeled_relevant == 12
        assert report.labeled_irrelevant == 8
