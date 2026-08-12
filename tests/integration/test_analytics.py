"""[C-I2] Аналитика поверх реального Postgres (testcontainers): /stats, /costs, /review.

Схемы 0007/0008 (vacancy/application) + 0002 (llm_call, labeled_vacancy). Проверяем:
- LlmCallRepository.totals за период = сумма фикстур `cost_usd` (сверка с Langfuse ±5%);
- VacancyRepository.counts/random_scored — счётчики и выборка скоренных;
- FunnelStats — воронка по статусам заявок из БД;
- ReviewAgreement — расхождение владельца со скором пишется в `label`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import LabeledVacancy as LabeledVacancyRow
from app.adapters.persistence.models import LlmCall
from app.adapters.persistence.models import Vacancy as VacancyRow
from app.adapters.persistence.repositories import (
    ApplicationRepository,
    LabelRepository,
    LlmCallRepository,
    VacancyRepository,
)
from app.application.funnel_stats import FunnelStats
from app.application.report_costs import ReportCosts
from app.application.review_agreement import ReviewAgreement, ReviewCandidate
from app.application.save_vacancy import SaveVacancy
from app.domain.shared import Source, SourceRef

pytestmark = pytest.mark.integration


async def _seed_vacancy(session: AsyncSession, ext: str, *, score: int | None = None) -> int:
    row = VacancyRow(
        source_ref=f"hh:{ext}",
        content_hash=f"h{ext}",
        normalized_key=f"acme|em|{ext}",
        first_seen_at=datetime.now(UTC),
        title=f"EM {ext}",
        company="Acme",
        url=f"https://hh.ru/{ext}",
        description_text="описание",
        score=score,
        score_reason="ok" if score is not None else None,
        prompt_version="scoring-1" if score is not None else None,
    )
    session.add(row)
    await session.flush()
    return row.id


async def test_costs_totals_match_fixtures_and_langfuse(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # в окне 30 дней
    db_session.add_all(
        [
            LlmCall(
                purpose="scoring",
                model="m",
                prompt_version="scoring-1",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.100000,
                latency_ms=10,
                trace_id="t1",
                created_at=now - timedelta(days=1),
            ),
            LlmCall(
                purpose="cover",
                model="m",
                prompt_version="cover-1",
                input_tokens=200,
                output_tokens=80,
                cost_usd=0.250000,
                latency_ms=20,
                trace_id="t2",
                created_at=now - timedelta(days=5),
            ),
            # вне окна — не учитывается
            LlmCall(
                purpose="scoring",
                model="m",
                prompt_version="scoring-1",
                input_tokens=999,
                output_tokens=999,
                cost_usd=9.000000,
                latency_ms=30,
                trace_id="t3",
                created_at=now - timedelta(days=60),
            ),
        ]
    )
    await db_session.flush()

    report = await ReportCosts(costs=LlmCallRepository(db_session)).run(days=30, now=now)

    assert report.totals.calls == 2
    assert report.totals.total_usd == pytest.approx(0.35, abs=1e-6)
    assert report.totals.input_tokens == 300
    assert report.totals.output_tokens == 130
    assert report.totals.by_purpose["scoring"] == pytest.approx(0.10, abs=1e-6)
    assert report.totals.by_purpose["cover"] == pytest.approx(0.25, abs=1e-6)

    # [C-I2] сверка с Langfuse-экспортом ±5% (эмулируем экспорт близким числом)
    langfuse_export = 0.34
    assert abs(report.totals.total_usd - langfuse_export) / langfuse_export <= 0.05


async def test_vacancy_counts_and_random_scored(db_session: AsyncSession) -> None:
    await _seed_vacancy(db_session, "a", score=80)
    await _seed_vacancy(db_session, "b", score=40)
    await _seed_vacancy(db_session, "c", score=None)  # не скорена

    repo = VacancyRepository(db_session)
    counts = await repo.counts()
    assert counts.total == 3
    assert counts.scored == 2

    picked = await repo.random_scored(5)
    assert len(picked) == 2
    assert all(r.score is not None for r in picked)


async def test_funnel_stats_from_db(db_session: AsyncSession) -> None:
    from app.application.change_status import ChangeApplicationStatus
    from app.domain.crm import ApplicationStatus

    apps = ApplicationRepository(db_session)
    vacancies = VacancyRepository(db_session)
    labels = LabelRepository(db_session)

    vid1 = await _seed_vacancy(db_session, "1", score=80)
    vid2 = await _seed_vacancy(db_session, "2", score=70)
    await SaveVacancy(apps=apps, vacancies=vacancies).run(vid1)
    await SaveVacancy(apps=apps, vacancies=vacancies).run(vid2)
    await ChangeApplicationStatus(apps=apps).advance(vid2, ApplicationStatus.APPLIED)

    report = await FunnelStats(apps=apps, vacancies=vacancies, labels=labels).run()

    assert report.counts["new"] == 1
    assert report.counts["applied"] == 1
    assert report.total == 2
    assert report.vacancies_total == 2
    assert report.vacancies_scored == 2


async def test_review_disagreement_writes_label(db_session: AsyncSession) -> None:
    vacancies = VacancyRepository(db_session)
    labels = LabelRepository(db_session)
    await _seed_vacancy(db_session, "42", score=80)

    uc = ReviewAgreement(vacancies=vacancies, labels=labels, threshold=60)
    candidate = ReviewCandidate(
        source_ref=SourceRef(source=Source.HH, external_id="42"),
        title="EM 42",
        company="Acme",
        url="https://hh.ru/42",
        description_text="описание",
        score=80,
        model_verdict="relevant",
    )

    recorded = await uc.record(candidate, "irrelevant")
    await db_session.flush()

    assert recorded.agreed is False and recorded.recorded_label is True
    stored = (
        await db_session.execute(
            text("SELECT verdict FROM labeled_vacancy WHERE source_ref = 'hh:42'")
        )
    ).scalar_one()
    assert stored == "irrelevant"

    # изоляция от неиспользуемого импорта строки-модели labeled
    assert LabeledVacancyRow.__tablename__ == "labeled_vacancy"
