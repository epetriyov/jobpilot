"""Реализации repository-портов поверх SQLAlchemy (contracts/repositories.md).

Конверсия ORM ↔ домен — здесь; наружу доменные типы/DTO, не ORM.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import JobRun, LabeledVacancy, LlmCall, SeenVacancy
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy, content_hash
from app.ports.llm import LlmCallRecord
from app.ports.repositories import LabeledVacancy as LabeledVacancyDTO


def _parse_source_ref(key: str) -> SourceRef:
    parts = key.split(":")
    source = Source(parts[0])
    if source is Source.SITE:
        return SourceRef(source=source, site_name=parts[1], external_id=":".join(parts[2:]))
    return SourceRef(source=source, external_id=":".join(parts[1:]))


class SeenVacancyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_seen(self, ref: SourceRef) -> bool:
        result = await self._session.execute(
            select(SeenVacancy.id).where(SeenVacancy.source_ref == ref.as_key())
        )
        return result.first() is not None

    async def mark_seen(self, vacancy: Vacancy) -> None:
        """Идемпотентно (S1): конфликт по source_ref не трогает first_seen_at."""
        stmt = (
            insert(SeenVacancy)
            .values(
                source_ref=vacancy.source_ref.as_key(),
                content_hash=content_hash(vacancy),
                normalized_key=vacancy.normalized_key(),
                first_seen_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["source_ref"])
        )
        await self._session.execute(stmt)

    async def find_duplicate(self, normalized_key: str, within_days: int = 30) -> str | None:
        cutoff = datetime.now(UTC) - timedelta(days=within_days)
        result = await self._session.execute(
            select(SeenVacancy.source_ref)
            .where(SeenVacancy.normalized_key == normalized_key)
            .where(SeenVacancy.first_seen_at >= cutoff)
            .order_by(SeenVacancy.first_seen_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_digest_sent(self, refs: Sequence[SourceRef], at: datetime) -> None:
        if not refs:
            return
        await self._session.execute(
            update(SeenVacancy)
            .where(SeenVacancy.source_ref.in_([r.as_key() for r in refs]))
            .values(digest_sent_at=at)
        )


class LabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, labeled: LabeledVacancyDTO) -> None:
        self._session.add(
            LabeledVacancy(
                source_ref=labeled.source_ref.as_key(),
                title=labeled.title,
                company=labeled.company,
                url=labeled.url,
                description_text=labeled.description_text,
                verdict=labeled.verdict,
            )
        )

    async def recent(self, limit: int = 10) -> list[LabeledVacancyDTO]:
        result = await self._session.execute(
            select(LabeledVacancy).order_by(LabeledVacancy.created_at.desc()).limit(limit)
        )
        return [
            LabeledVacancyDTO(
                source_ref=_parse_source_ref(row.source_ref),
                title=row.title,
                company=row.company,
                url=row.url,
                description_text=row.description_text,
                verdict=cast("Literal['relevant', 'irrelevant']", row.verdict),
            )
            for row in result.scalars()
        ]


class LlmCallRepository:
    """Реализация LlmCallRecorderPort — учёт O1."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, call: LlmCallRecord) -> None:
        self._session.add(
            LlmCall(
                purpose=call.purpose,
                model=call.model,
                prompt_version=call.prompt_version,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
                latency_ms=call.latency_ms,
                trace_id=call.trace_id,
            )
        )


class JobRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, job_name: str, trace_id: str) -> int:
        run = JobRun(
            job_name=job_name,
            status="running",
            trace_id=trace_id,
            started_at=datetime.now(UTC),
        )
        self._session.add(run)
        await self._session.flush()
        return run.id

    async def finish(
        self,
        run_id: int,
        *,
        status: Literal["success", "partial", "error"],
        items_in: int = 0,
        items_out: int = 0,
        error: str | None = None,
    ) -> None:
        await self._session.execute(
            update(JobRun)
            .where(JobRun.id == run_id)
            .values(
                status=status,
                items_in=items_in,
                items_out=items_out,
                error=error,
                finished_at=datetime.now(UTC),
            )
        )
