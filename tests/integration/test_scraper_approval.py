"""[T506][US3] ScraperApprovalRepository: is_approved/approve/approved_sites, идемпотентность.

Реальный Postgres (testcontainers). Факт одобрения переживает рестарт (персист);
повторный approve не меняет момент первого одобрения (идемпотентно).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.adapters.persistence.repositories import ScraperApprovalRepository

pytestmark = pytest.mark.integration


async def test_unapproved_by_default(db_session) -> None:
    repo = ScraperApprovalRepository(db_session)
    assert await repo.is_approved("yandex") is False
    assert await repo.approved_sites() == set()


async def test_approve_then_is_approved(db_session) -> None:
    repo = ScraperApprovalRepository(db_session)
    await repo.approve("yandex", chat_id=100500)
    await db_session.commit()
    assert await repo.is_approved("yandex") is True
    assert await repo.approved_sites() == {"yandex"}


async def test_approve_is_idempotent(db_session) -> None:
    repo = ScraperApprovalRepository(db_session)
    await repo.approve("vk", chat_id=100500)
    await db_session.commit()
    first_at = (
        await db_session.execute(
            text("SELECT approved_at FROM scraper_approval WHERE site_name = 'vk'")
        )
    ).scalar_one()

    await repo.approve("vk", chat_id=999)  # повторное одобрение (другой chat_id)
    await db_session.commit()
    rows = (
        await db_session.execute(text("SELECT count(*) FROM scraper_approval WHERE site_name='vk'"))
    ).scalar_one()
    second_at = (
        await db_session.execute(
            text("SELECT approved_at FROM scraper_approval WHERE site_name = 'vk'")
        )
    ).scalar_one()

    assert rows == 1  # без дублей
    assert first_at == second_at  # момент первого одобрения не сдвинут


async def test_multiple_sites(db_session) -> None:
    repo = ScraperApprovalRepository(db_session)
    await repo.approve("yandex", chat_id=100500)
    await repo.approve("sber", chat_id=100500)
    await db_session.commit()
    assert await repo.approved_sites() == {"yandex", "sber"}
