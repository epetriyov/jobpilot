"""Use case SaveVacancy (спека 006, US2, [C-U4]): 💾 → Application(new) + VacancySaved.

Повторное 💾 той же вакансии не плодит дубль — возвращает тот же Application (C1).
"""

from __future__ import annotations

from typing import Literal

import structlog

from app.domain.crm import Application, VacancySaved
from app.ports.repositories import ApplicationRepositoryPort, VacancyRepositoryPort

log = structlog.get_logger("application.save_vacancy")

Outcome = Literal["saved", "already", "not_found"]


class SaveVacancy:
    def __init__(
        self, *, apps: ApplicationRepositoryPort, vacancies: VacancyRepositoryPort
    ) -> None:
        self._apps = apps
        self._vacancies = vacancies

    async def run(self, vacancy_id: int) -> tuple[Outcome, VacancySaved | None]:
        if await self._vacancies.get_by_id(vacancy_id) is None:
            return "not_found", None
        if await self._apps.get_by_vacancy(vacancy_id) is not None:
            # C1: один активный Application на вакансию — дубль не создаём ([C-U4]).
            return "already", None
        app, event = Application.create(vacancy_id=vacancy_id)
        await self._apps.save(app)
        log.info("vacancy_saved", vacancy_id=vacancy_id)
        return "saved", event
