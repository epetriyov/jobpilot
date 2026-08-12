"""Contract-тест ReportCosts (спека 006, US4, T6C-2): сумма затрат LLM за период.

`/costs` = агрегат `llm_call.cost_usd`/токенов за окно [now-days, now]. Логика окна
и проброс агрегата — чистые (fake reader), сверка с фикстурами БД — в integration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.application.report_costs import CostReport, ReportCosts
from app.ports.repositories import CostTotals


class FakeCostReader:
    def __init__(self, totals: CostTotals) -> None:
        self._totals = totals
        self.calls: list[tuple[datetime, datetime]] = []

    async def totals(self, since: datetime, until: datetime) -> CostTotals:
        self.calls.append((since, until))
        return self._totals


_TOTALS = CostTotals(
    total_usd=1.23,
    input_tokens=1000,
    output_tokens=500,
    calls=7,
    by_purpose={"scoring": 1.0, "cover": 0.23},
)


class TestReportCosts:
    async def test_window_is_last_n_days(self) -> None:
        reader = FakeCostReader(_TOTALS)
        now = datetime(2026, 8, 12, tzinfo=UTC)
        report = await ReportCosts(costs=reader).run(days=30, now=now)

        assert isinstance(report, CostReport)
        assert report.days == 30
        assert report.until == now
        assert report.since == now - timedelta(days=30)
        assert reader.calls == [(now - timedelta(days=30), now)]

    async def test_totals_passthrough(self) -> None:
        report = await ReportCosts(costs=FakeCostReader(_TOTALS)).run(days=7)
        assert report.totals == _TOTALS
        assert report.totals.total_usd == 1.23
        assert report.totals.by_purpose["scoring"] == 1.0
