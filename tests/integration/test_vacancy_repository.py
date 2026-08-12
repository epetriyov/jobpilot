"""Integration: реальный VacancyRepository поверх `vacancy` (T6A-4).

Та же семантика, что и у fake из contract-теста: get/get_by_id/list/search_saved
над мигрированной таблицей. Доказывает фундамент для CRM/MCP/аналитики (6B/6E/6F).
"""

from __future__ import annotations

import pytest

from app.adapters.persistence.repositories import SeenVacancyRepository, VacancyRepository
from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy
from app.ports.repositories import VacancyListFilter

pytestmark = pytest.mark.integration


def _vacancy(ext: str, *, title: str, company: str, canary: bool = False) -> Vacancy:
    v = Vacancy.create(
        source_ref=SourceRef(source=Source.HH, external_id=ext),
        title=title,
        company=company,
        url=f"https://hh.ru/vacancy/{ext}",
        description_raw=f"<p>Описание {title} в {company}</p>",
        salary=Salary(from_=300_000, currency="RUR"),
    )
    v.canary = canary
    return v


async def _seed(session) -> None:  # type: ignore[no-untyped-def]
    seen = SeenVacancyRepository(session)
    await seen.mark_seen(_vacancy("1", title="Engineering Manager", company="Acme"))
    await seen.mark_seen(_vacancy("2", title="Team Lead", company="Globex", canary=True))
    await seen.mark_seen(_vacancy("3", title="Head of Platform", company="Initech"))
    # скорим двух из трёх
    from app.domain.relevance import Score

    await seen.save_score(
        SourceRef(source=Source.HH, external_id="1"),
        Score(value=82, reason="матч", prompt_version="scoring/1", model="fake/model"),
    )
    await seen.save_score(
        SourceRef(source=Source.HH, external_id="2"),
        Score(value=40, reason="слабо", prompt_version="scoring/1", model="fake/model"),
    )
    await session.commit()


async def test_get_and_get_by_id(db_session) -> None:  # type: ignore[no-untyped-def]
    await _seed(db_session)
    repo = VacancyRepository(db_session)

    by_ref = await repo.get(SourceRef(source=Source.HH, external_id="1"))
    assert by_ref is not None
    assert by_ref.title == "Engineering Manager"
    assert by_ref.score == 82
    assert by_ref.salary_text and "300" in by_ref.salary_text

    by_id = await repo.get_by_id(by_ref.id)
    assert by_id is not None and by_id.source_ref.as_key() == "hh:1"

    assert await repo.get(SourceRef(source=Source.HH, external_id="404")) is None
    assert await repo.get_by_id(999_999) is None


async def test_list_filters_and_recency(db_session) -> None:  # type: ignore[no-untyped-def]
    await _seed(db_session)
    repo = VacancyRepository(db_session)

    scored = await repo.list(VacancyListFilter(scored_only=True))
    assert {r.source_ref.as_key() for r in scored} == {"hh:1", "hh:2"}

    strong = await repo.list(VacancyListFilter(min_score=60))
    assert {r.source_ref.as_key() for r in strong} == {"hh:1"}

    limited = await repo.list(VacancyListFilter(limit=2))
    assert len(limited) == 2

    rows = await repo.list(VacancyListFilter())
    canary = next(r for r in rows if r.source_ref.as_key() == "hh:2")
    assert canary.canary is True


async def test_search_saved(db_session) -> None:  # type: ignore[no-untyped-def]
    await _seed(db_session)
    repo = VacancyRepository(db_session)

    assert {r.source_ref.as_key() for r in await repo.search_saved("globex")} == {"hh:2"}
    assert {r.source_ref.as_key() for r in await repo.search_saved("MANAGER")} == {"hh:1"}
    assert await repo.search_saved("несуществующий") == []
