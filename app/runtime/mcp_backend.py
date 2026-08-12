"""Композиционный корень MCP: `McpBackend` поверх Services/репозиториев (этап 6F).

Здесь (в `app/runtime`, НЕ в `app/mcp`) живёт вся работа с БД — так слой `app/mcp`
остаётся тонким и не тянет persistence (MCP1). Разделение ролей БД (MCP4, [P-I1]):
read-инструменты ходят через `read_session_factory` (роль `mcp_ro`, GRANT SELECT),
write-инструменты (`set_status`, `run_digest`) — через основной пул Services.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.repositories import (
    ApplicationRepository,
    LabelRepository,
    LlmCallRepository,
    VacancyRepository,
)
from app.application.funnel_stats import FunnelStats
from app.application.report_costs import ReportCosts
from app.domain.crm import ApplicationStatus, RejectStage
from app.ports.repositories import VacancyListFilter, VacancyRecord
from app.runtime.composition import Services

log = structlog.get_logger("runtime.mcp_backend")

_LINEAR_STATUSES = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
}


def _vacancy_dict(record: VacancyRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


class ServicesMcpBackend:
    """`McpBackend` над Services: read — под read-ролью, write — под основной ролью."""

    def __init__(
        self,
        *,
        services: Services,
        read_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._services = services
        self._read = read_session_factory

    # --- read-инструменты (роль mcp_ro) ---

    async def list_vacancies(
        self, *, min_score: int | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        filter_ = VacancyListFilter(
            scored_only=min_score is not None, min_score=min_score, limit=limit
        )
        async with self._read() as session:
            rows = await VacancyRepository(session).list(filter_)
        return [_vacancy_dict(r) for r in rows]

    async def get_vacancy(self, vacancy_id: int) -> dict[str, Any] | None:
        async with self._read() as session:
            record = await VacancyRepository(session).get_by_id(vacancy_id)
        return _vacancy_dict(record) if record else None

    async def search_saved(self, query: str) -> list[dict[str, Any]]:
        async with self._read() as session:
            rows = await VacancyRepository(session).search_saved(query)
        return [_vacancy_dict(r) for r in rows]

    async def get_costs(self, days: int = 30) -> dict[str, Any]:
        async with self._read() as session:
            report = await ReportCosts(costs=LlmCallRepository(session)).run(days=days)
        return report.model_dump(mode="json")

    async def funnel_stats(self) -> dict[str, Any]:
        async with self._read() as session:
            report = await FunnelStats(
                apps=ApplicationRepository(session),
                vacancies=VacancyRepository(session),
                labels=LabelRepository(session),
            ).run()
        return report.model_dump(mode="json")

    # --- write-инструменты (белый список MCP2, основной пул) ---

    async def set_status(
        self, vacancy_id: int, status: str, reject_stage: str | None = None
    ) -> dict[str, Any]:
        """Перевод заявки через статусную машину; неизвестный статус → illegal (C2)."""
        try:
            target = ApplicationStatus(status)
        except ValueError:
            return {"outcome": "illegal", "vacancy_id": vacancy_id, "status": status}

        if target is ApplicationStatus.REJECTED:
            stage = RejectStage(reject_stage) if reject_stage else None
            outcome = await self._services.reject_application(vacancy_id, stage)
        elif target in _LINEAR_STATUSES:
            outcome = await self._services.advance_application(vacancy_id, target)
        else:
            outcome = "illegal"
        return {"outcome": outcome, "vacancy_id": vacancy_id, "status": status}

    async def run_digest(self, dry_run: bool = True) -> dict[str, Any]:
        result = await self._services.run_digest(dry_run=dry_run)
        return {
            "dry_run": dry_run,
            "discovered": result.discovered,
            "cards_sent": result.cards_sent,
            "partial": result.partial,
            "label": "ТЕСТ" if dry_run else "боевой",
        }
