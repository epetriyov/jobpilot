"""Use case ReportCosts (спека 006, US4, T6C-2, [C-I2]): затраты LLM за период.

`/costs` = агрегат `llm_call.cost_usd`/токенов за окно [now-days, now]. Сумма
сверяется с Langfuse-экспортом ±5% (integration). Только чтение (инвариант O1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from app.ports.repositories import CostTotals, LlmCostReaderPort


class CostReport(BaseModel):
    """Отчёт /costs: период + агрегат затрат."""

    model_config = ConfigDict(frozen=True)

    days: int
    since: datetime
    until: datetime
    totals: CostTotals


class ReportCosts:
    def __init__(self, *, costs: LlmCostReaderPort) -> None:
        self._costs = costs

    async def run(self, days: int = 30, now: datetime | None = None) -> CostReport:
        until = now if now is not None else datetime.now(UTC)
        since = until - timedelta(days=days)
        totals = await self._costs.totals(since, until)
        return CostReport(days=days, since=since, until=until, totals=totals)
