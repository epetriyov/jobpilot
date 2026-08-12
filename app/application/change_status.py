"""Use case ChangeApplicationStatus (спека 006, US2): переходы/раунды/отказ/удаление.

Все решения — через доменные методы Application (§3.3); недопустимое действие →
IllegalTransition ловится и превращается в вежливый отказ, состояние неизменно (C2).
"""

from __future__ import annotations

from typing import Literal

import structlog

from app.domain.crm import (
    ApplicationStatus,
    IllegalTransition,
    InterviewRoundKind,
    RejectStage,
)
from app.ports.repositories import ApplicationRepositoryPort

log = structlog.get_logger("application.change_status")

Outcome = Literal["ok", "illegal", "not_found", "deleted"]


class ChangeApplicationStatus:
    def __init__(self, *, apps: ApplicationRepositoryPort) -> None:
        self._apps = apps

    async def advance(self, vacancy_id: int, to: ApplicationStatus) -> Outcome:
        """Линейный переход вперёд new→applied→interview→offer (§3.3)."""
        app = await self._apps.get_by_vacancy(vacancy_id)
        if app is None:
            return "not_found"
        try:
            app.transition(to)
        except IllegalTransition:
            return "illegal"
        await self._apps.save(app)
        log.info("application_status_changed", vacancy_id=vacancy_id, to=str(to))
        return "ok"

    async def add_round(self, vacancy_id: int, kind: InterviewRoundKind) -> Outcome:
        """Добавить раунд собеседования (только в interview, по возрастанию — C2)."""
        app = await self._apps.get_by_vacancy(vacancy_id)
        if app is None:
            return "not_found"
        try:
            app.add_round(kind)
        except IllegalTransition:
            return "illegal"
        await self._apps.save(app)
        log.info("interview_round_added", vacancy_id=vacancy_id, kind=str(kind))
        return "ok"

    async def reject(self, vacancy_id: int, stage: RejectStage | None) -> Outcome:
        """Отказ с обязательным валидным этапом (§3.3, [C-U3])."""
        app = await self._apps.get_by_vacancy(vacancy_id)
        if app is None:
            return "not_found"
        try:
            app.reject(stage)
        except IllegalTransition:
            return "illegal"
        await self._apps.save(app)
        log.info("application_rejected", vacancy_id=vacancy_id, stage=str(stage))
        return "ok"

    async def delete(self, vacancy_id: int) -> Outcome:
        """🗑 hard-delete из любого статуса (C1); вакансия остаётся в `vacancy`."""
        app = await self._apps.get_by_vacancy(vacancy_id)
        if app is None:
            return "not_found"
        await self._apps.delete(vacancy_id)
        log.info("application_deleted", vacancy_id=vacancy_id)
        return "deleted"
