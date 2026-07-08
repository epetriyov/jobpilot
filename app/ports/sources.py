"""VacancySourcePort (DOMAIN.md §3.1): адаптеры источников вакансий."""

from __future__ import annotations

from typing import Protocol

from app.domain.sourcing import Vacancy


class VacancySourcePort(Protocol):
    """Источник вакансий: hh, getmatch, 7 сайтов (адаптеры этапов 1/4/5)."""

    name: str

    async def fetch(self) -> list[Vacancy]: ...
