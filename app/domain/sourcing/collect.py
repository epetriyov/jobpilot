"""Сбор из нескольких источников с изоляцией падений (S4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.domain.sourcing.events import SourceFetchFailed
from app.domain.sourcing.vacancy import Vacancy

SourceFetcher = Callable[[], list[Vacancy]]


@dataclass
class CollectResult:
    vacancies: list[Vacancy] = field(default_factory=list)
    failures: list[SourceFetchFailed] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        """Хоть один источник упал → job_run.status=partial ([S-U4])."""
        return bool(self.failures) and bool(self.vacancies)


def collect_from_sources(sources: dict[str, SourceFetcher]) -> CollectResult:
    result = CollectResult()
    for name, fetch in sources.items():
        try:
            result.vacancies.extend(fetch())
        except Exception as exc:
            result.failures.append(SourceFetchFailed(source=name, error=str(exc)))
    return result
