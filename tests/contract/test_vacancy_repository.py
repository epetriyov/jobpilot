"""Contract-тест `VacancyRepositoryPort` на fake (T6A-4).

Надстройка над хранилищем `vacancy` для CRM/MCP/аналитики: `get(source_ref)`,
`get_by_id`, `list(filter)`, `search_saved(query)`. Семантика фиксируется на
in-memory fake; реальный `VacancyRepository` проверяется integration-тестом.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.shared import Source, SourceRef
from app.ports.repositories import (
    VacancyListFilter,
    VacancyRecord,
    VacancyRepositoryPort,
)

pytestmark = pytest.mark.asyncio


class FakeVacancyRepository:
    """In-memory реализация VacancyRepositoryPort для contract-теста."""

    def __init__(self, records: list[VacancyRecord]) -> None:
        self._records = list(records)

    async def get(self, source_ref: SourceRef) -> VacancyRecord | None:
        key = source_ref.as_key()
        return next((r for r in self._records if r.source_ref.as_key() == key), None)

    async def get_by_id(self, vacancy_id: int) -> VacancyRecord | None:
        return next((r for r in self._records if r.id == vacancy_id), None)

    async def list(self, filter_: VacancyListFilter) -> list[VacancyRecord]:
        rows = self._records
        if filter_.scored_only:
            rows = [r for r in rows if r.score is not None]
        if filter_.min_score is not None:
            rows = [r for r in rows if r.score is not None and r.score >= filter_.min_score]
        rows = sorted(rows, key=lambda r: r.first_seen_at, reverse=True)
        return rows[: filter_.limit]

    async def search_saved(self, query: str) -> list[VacancyRecord]:
        q = query.casefold()
        rows = [
            r
            for r in self._records
            if q in r.title.casefold()
            or q in r.company.casefold()
            or q in r.description_text.casefold()
        ]
        return sorted(rows, key=lambda r: r.first_seen_at, reverse=True)


def _record(
    *,
    vid: int,
    ext: str,
    title: str,
    company: str,
    score: int | None,
    seen: datetime,
) -> VacancyRecord:
    return VacancyRecord(
        id=vid,
        source_ref=SourceRef(source=Source.HH, external_id=ext),
        title=title,
        company=company,
        url=f"https://hh.ru/vacancy/{ext}",
        description_text=f"Описание {title} в {company}",
        salary_text="от 300 000 RUR",
        score=score,
        score_reason=None if score is None else "матч",
        duplicate_of=None,
        canary=False,
        first_seen_at=seen,
    )


@pytest.fixture()
def repo() -> FakeVacancyRepository:
    now = datetime.now(UTC)
    records = [
        _record(vid=1, ext="1", title="Engineering Manager", company="Acme", score=82, seen=now),
        _record(
            vid=2,
            ext="2",
            title="Team Lead",
            company="Globex",
            score=40,
            seen=now - timedelta(days=1),
        ),
        _record(
            vid=3,
            ext="3",
            title="Head of Platform",
            company="Initech",
            score=None,
            seen=now - timedelta(days=2),
        ),
    ]
    return FakeVacancyRepository(records)


def _is_port(repo: VacancyRepositoryPort) -> VacancyRepositoryPort:
    return repo  # структурная проверка типом на этапе mypy


async def test_get_by_source_ref(repo: FakeVacancyRepository) -> None:
    _is_port(repo)
    got = await repo.get(SourceRef(source=Source.HH, external_id="1"))
    assert got is not None
    assert got.id == 1
    assert got.title == "Engineering Manager"
    assert got.score == 82
    assert await repo.get(SourceRef(source=Source.HH, external_id="404")) is None


async def test_get_by_id(repo: FakeVacancyRepository) -> None:
    got = await repo.get_by_id(2)
    assert got is not None
    assert got.company == "Globex"
    assert await repo.get_by_id(999) is None


async def test_list_orders_by_recency_and_limits(repo: FakeVacancyRepository) -> None:
    rows = await repo.list(VacancyListFilter(limit=2))
    assert [r.id for r in rows] == [1, 2]  # новейшие первыми


async def test_list_scored_only_and_min_score(repo: FakeVacancyRepository) -> None:
    scored = await repo.list(VacancyListFilter(scored_only=True))
    assert {r.id for r in scored} == {1, 2}  # id=3 без скора отфильтрован
    strong = await repo.list(VacancyListFilter(min_score=60))
    assert {r.id for r in strong} == {1}


async def test_search_saved_is_case_insensitive(repo: FakeVacancyRepository) -> None:
    by_company = await repo.search_saved("globex")
    assert {r.id for r in by_company} == {2}
    by_title = await repo.search_saved("MANAGER")
    assert {r.id for r in by_title} == {1}
    assert await repo.search_saved("несуществующий") == []
