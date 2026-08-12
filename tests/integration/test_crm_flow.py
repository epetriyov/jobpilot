"""[C-I1] CRM полный цикл через репозитории поверх реального Postgres (testcontainers).

Схема 0008 (application + interview_round) + сквозной путь заявки:
💾 → applied → interview(hr) → interview(tech-1) → offer; C1 (uq vacancy_id);
удаление освобождает вакансию под новое 💾.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import ApplicationRow
from app.adapters.persistence.models import Vacancy as VacancyRow
from app.adapters.persistence.repositories import ApplicationRepository, VacancyRepository
from app.application.add_interview_details import AddInterviewDetails
from app.application.change_status import ChangeApplicationStatus
from app.application.save_vacancy import SaveVacancy
from app.domain.crm import ApplicationStatus, InterviewRoundKind, RejectStage

pytestmark = pytest.mark.integration


def test_stage6b_schema_present(pg_url: str, alembic_config) -> None:
    """T6B-5: application + interview_round с ключевыми ограничениями."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    from sqlalchemy import create_engine

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"vacancy", "application", "interview_round"} <= tables

    app_cols = {c["name"] for c in inspector.get_columns("application")}
    assert {"vacancy_id", "status", "reject_stage", "interview_url", "notes"} <= app_cols
    uqs = {u["name"] for u in inspector.get_unique_constraints("application")}
    assert "uq_application_vacancy" in uqs  # C1

    round_uqs = {u["name"] for u in inspector.get_unique_constraints("interview_round")}
    assert {"uq_interview_round_ordinal", "uq_interview_round_kind"} <= round_uqs
    fks = inspector.get_foreign_keys("interview_round")
    assert any(fk["referred_table"] == "application" for fk in fks)


async def _seed_vacancy(session: AsyncSession, vacancy_id: int = 1) -> int:
    from datetime import UTC, datetime

    row = VacancyRow(
        source_ref=f"hh:{vacancy_id}",
        content_hash=f"h{vacancy_id}",
        normalized_key=f"acme|em|{vacancy_id}",
        first_seen_at=datetime.now(UTC),
        title="EM",
        company="Acme",
        url="u",
    )
    session.add(row)
    await session.flush()
    return row.id


async def test_full_forward_cycle(db_session: AsyncSession) -> None:
    """[C-I1] карточка → 💾 → applied → interview(hr) → interview(tech-1) → offer."""
    vacancy_id = await _seed_vacancy(db_session)
    apps = ApplicationRepository(db_session)
    vacancies = VacancyRepository(db_session)

    outcome, event = await SaveVacancy(apps=apps, vacancies=vacancies).run(vacancy_id)
    assert outcome == "saved" and event is not None

    change = ChangeApplicationStatus(apps=apps)
    assert await change.advance(vacancy_id, ApplicationStatus.APPLIED) == "ok"
    assert await change.advance(vacancy_id, ApplicationStatus.INTERVIEW) == "ok"
    assert await change.add_round(vacancy_id, InterviewRoundKind.HR) == "ok"
    assert await change.add_round(vacancy_id, InterviewRoundKind.TECH_1) == "ok"
    assert await change.advance(vacancy_id, ApplicationStatus.OFFER) == "ok"

    persisted = await apps.get_by_vacancy(vacancy_id)
    assert persisted is not None
    assert persisted.status is ApplicationStatus.OFFER
    assert [r.kind for r in persisted.interview_rounds] == [
        InterviewRoundKind.HR,
        InterviewRoundKind.TECH_1,
    ]
    assert [r.ordinal for r in persisted.interview_rounds] == [1, 2]


async def test_illegal_transition_not_persisted(db_session: AsyncSession) -> None:
    vacancy_id = await _seed_vacancy(db_session, 2)
    apps = ApplicationRepository(db_session)
    await SaveVacancy(apps=apps, vacancies=VacancyRepository(db_session)).run(vacancy_id)

    change = ChangeApplicationStatus(apps=apps)
    # new → interview (мимо applied) — недопустим (C2)
    assert await change.advance(vacancy_id, ApplicationStatus.INTERVIEW) == "illegal"
    persisted = await apps.get_by_vacancy(vacancy_id)
    assert persisted is not None and persisted.status is ApplicationStatus.NEW


async def test_reject_persists_stage(db_session: AsyncSession) -> None:
    vacancy_id = await _seed_vacancy(db_session, 3)
    apps = ApplicationRepository(db_session)
    await SaveVacancy(apps=apps, vacancies=VacancyRepository(db_session)).run(vacancy_id)
    change = ChangeApplicationStatus(apps=apps)
    await change.advance(vacancy_id, ApplicationStatus.APPLIED)

    assert await change.reject(vacancy_id, RejectStage.HR) == "ok"
    persisted = await apps.get_by_vacancy(vacancy_id)
    assert persisted is not None
    assert persisted.status is ApplicationStatus.REJECTED
    assert persisted.reject_stage is RejectStage.HR


async def test_add_interview_details_keeps_status(db_session: AsyncSession) -> None:
    """[C-U5] ручной «➕ собес» дополняет детали, статус не меняет (C3)."""
    vacancy_id = await _seed_vacancy(db_session, 4)
    apps = ApplicationRepository(db_session)
    await SaveVacancy(apps=apps, vacancies=VacancyRepository(db_session)).run(vacancy_id)
    await ChangeApplicationStatus(apps=apps).advance(vacancy_id, ApplicationStatus.APPLIED)

    outcome = await AddInterviewDetails(apps=apps).run(
        vacancy_id, url="https://meet.example/x", notes="в 15:00"
    )
    assert outcome == "ok"
    persisted = await apps.get_by_vacancy(vacancy_id)
    assert persisted is not None
    assert persisted.status is ApplicationStatus.APPLIED
    assert persisted.interview_url == "https://meet.example/x"


async def test_c1_unique_and_delete_frees(db_session: AsyncSession) -> None:
    """C1: один активный Application на вакансию; удаление освобождает под новое 💾."""
    vacancy_id = await _seed_vacancy(db_session, 5)
    apps = ApplicationRepository(db_session)
    vacancies = VacancyRepository(db_session)
    await SaveVacancy(apps=apps, vacancies=vacancies).run(vacancy_id)

    # прямой второй insert той же vacancy_id нарушает uq (C1) — в savepoint,
    # чтобы откат затронул только дубль, а не сохранённую заявку и вакансию
    savepoint = await db_session.begin_nested()
    db_session.add(ApplicationRow(vacancy_id=vacancy_id, status="new"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await savepoint.rollback()

    # исходная заявка цела → hard-delete освобождает вакансию под новое 💾
    assert await ChangeApplicationStatus(apps=apps).delete(vacancy_id) == "deleted"
    assert await apps.get_by_vacancy(vacancy_id) is None
    # вакансия осталась в хранилище
    assert await vacancies.get_by_id(vacancy_id) is not None
    # повторное 💾 создаёт новый Application
    outcome, _ = await SaveVacancy(apps=apps, vacancies=vacancies).run(vacancy_id)
    assert outcome == "saved"


async def test_rejected_requires_stage_check(db_session: AsyncSession) -> None:
    """CHECK ck_application_rejected_has_stage: rejected без stage отвергается БД."""
    vacancy_id = await _seed_vacancy(db_session, 6)
    db_session.add(ApplicationRow(vacancy_id=vacancy_id, status="rejected", reject_stage=None))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_cascade_delete_removes_rounds(db_session: AsyncSession) -> None:
    vacancy_id = await _seed_vacancy(db_session, 7)
    apps = ApplicationRepository(db_session)
    await SaveVacancy(apps=apps, vacancies=VacancyRepository(db_session)).run(vacancy_id)
    change = ChangeApplicationStatus(apps=apps)
    await change.advance(vacancy_id, ApplicationStatus.APPLIED)
    await change.advance(vacancy_id, ApplicationStatus.INTERVIEW)
    await change.add_round(vacancy_id, InterviewRoundKind.HR)

    await change.delete(vacancy_id)
    remaining = await db_session.execute(text("SELECT count(*) FROM interview_round"))
    assert remaining.scalar_one() == 0
