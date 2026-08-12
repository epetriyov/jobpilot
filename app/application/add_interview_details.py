"""Use case AddInterviewDetails (спека 006, US3 ручной путь, [C-U5]).

«➕ собес»: дополняет interview_url/notes заявки. Статус НИКОГДА не меняется (C3).
Второй путь (LLM `hr_extract`) появляется в 6G поверх этой же точки — здесь нет LLM.
"""

from __future__ import annotations

from typing import Literal

import structlog

from app.ports.repositories import ApplicationRepositoryPort

log = structlog.get_logger("application.add_interview_details")

Outcome = Literal["ok", "not_found"]


class AddInterviewDetails:
    def __init__(self, *, apps: ApplicationRepositoryPort) -> None:
        self._apps = apps

    async def run(
        self, vacancy_id: int, *, url: str | None = None, notes: str | None = None
    ) -> Outcome:
        app = await self._apps.get_by_vacancy(vacancy_id)
        if app is None:
            # edge case: «➕ собес» на вакансию без Application → сначала 💾 Сохранить.
            return "not_found"
        app.add_interview_details(url=url, notes=notes)
        await self._apps.save(app)
        log.info("interview_details_added", vacancy_id=vacancy_id, has_url=url is not None)
        return "ok"
