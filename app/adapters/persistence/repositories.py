"""Реализации repository-портов поверх SQLAlchemy (contracts/repositories.md).

Конверсия ORM ↔ домен — здесь; наружу доменные типы/DTO, не ORM.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import (
    InboxMessageRow,
    JobRun,
    LabeledVacancy,
    LinkedInTarget,
    LlmCall,
    ScraperApproval,
    SeenVacancy,
)
from app.domain.correspondence import InboxMessage as InboxMessageDTO
from app.domain.networking import InviteDraft as InviteDraftDTO
from app.domain.networking import InviteStatus
from app.domain.relevance import Score, VacancySnapshot
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy, content_hash
from app.ports.llm import LlmCallRecord
from app.ports.repositories import LabeledVacancy as LabeledVacancyDTO
from app.ports.repositories import ScoredCandidate


def _parse_source_ref(key: str) -> SourceRef:
    parts = key.split(":")
    source = Source(parts[0])
    if source is Source.SITE:
        return SourceRef(source=source, site_name=parts[1], external_id=":".join(parts[2:]))
    return SourceRef(source=source, external_id=":".join(parts[1:]))


def _row_to_snapshot(row: SeenVacancy) -> VacancySnapshot:
    return VacancySnapshot(
        source_ref=_parse_source_ref(row.source_ref),
        title=row.title or "",
        company=row.company or "",
        url=row.url or "",
        description_text=row.description_text or "",
    )


def _salary_text(from_: int | None, to: int | None, currency: str | None) -> str | None:
    if from_ is None and to is None:
        return None
    parts = []
    if from_ is not None:
        parts.append(f"от {from_:,}".replace(",", " "))
    if to is not None:
        parts.append(f"до {to:,}".replace(",", " "))
    if currency:
        parts.append(currency)
    return " ".join(parts)


class SeenVacancyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_seen(self, ref: SourceRef) -> bool:
        result = await self._session.execute(
            select(SeenVacancy.id).where(SeenVacancy.source_ref == ref.as_key())
        )
        return result.first() is not None

    async def mark_seen(self, vacancy: Vacancy) -> None:
        """Идемпотентно (S1): конфликт по source_ref не трогает first_seen_at.

        С этапа 1 пишет и снапшот (title/company/url/текст/вилка) — карточки
        и разметка работают без повторного похода в источник.
        """
        stmt = (
            insert(SeenVacancy)
            .values(
                source_ref=vacancy.source_ref.as_key(),
                content_hash=content_hash(vacancy),
                normalized_key=vacancy.normalized_key(),
                first_seen_at=datetime.now(UTC),
                title=vacancy.title,
                company=vacancy.company,
                url=vacancy.url,
                description_text=vacancy.description_text,
                salary_from=vacancy.salary.from_,
                salary_to=vacancy.salary.to,
                salary_currency=vacancy.salary.currency,
            )
            .on_conflict_do_nothing(index_elements=["source_ref"])
        )
        await self._session.execute(stmt)

    async def unscored(self, prompt_version: str, limit: int = 200) -> list[VacancySnapshot]:
        """R1: без скора актуальной prompt_version; дубликаты (digest_sent_at
        проставлен при обнаружении) и строки без снапшота не скорятся."""
        result = await self._session.execute(
            select(SeenVacancy)
            .where(SeenVacancy.description_text.is_not(None))
            .where(SeenVacancy.digest_sent_at.is_(None))
            .where(
                (SeenVacancy.score.is_(None))
                | (SeenVacancy.prompt_version.is_distinct_from(prompt_version))
            )
            .order_by(SeenVacancy.first_seen_at.asc())
            .limit(limit)
        )
        return [_row_to_snapshot(row) for row in result.scalars()]

    async def save_score(self, ref: SourceRef, score: Score) -> None:
        await self._session.execute(
            update(SeenVacancy)
            .where(SeenVacancy.source_ref == ref.as_key())
            .values(
                score=score.value,
                score_reason=score.reason,
                prompt_version=score.prompt_version,
                score_model=score.model,
                scored_at=datetime.now(UTC),
            )
        )

    async def snapshot(self, ref: SourceRef) -> VacancySnapshot | None:
        result = await self._session.execute(
            select(SeenVacancy).where(SeenVacancy.source_ref == ref.as_key())
        )
        row = result.scalar_one_or_none()
        if row is None or row.description_text is None:
            return None
        return _row_to_snapshot(row)

    async def unsent_scored(self) -> list[ScoredCandidate]:
        result = await self._session.execute(
            select(SeenVacancy)
            .where(SeenVacancy.score.is_not(None))
            .where(SeenVacancy.digest_sent_at.is_(None))
        )
        return [
            ScoredCandidate(
                snapshot=_row_to_snapshot(row),
                score=Score(
                    value=row.score or 0,
                    reason=row.score_reason or "",
                    prompt_version=row.prompt_version or "",
                    model=row.score_model or "",
                ),
                salary_text=_salary_text(row.salary_from, row.salary_to, row.salary_currency),
            )
            for row in result.scalars()
        ]

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

    async def upsert(self, labeled: LabeledVacancyDTO) -> None:
        """Повторная разметка обновляет вердикт существующей записи (T112)."""
        result = await self._session.execute(
            select(LabeledVacancy).where(LabeledVacancy.source_ref == labeled.source_ref.as_key())
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.verdict = labeled.verdict
            return
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

    async def counts(self) -> tuple[int, int]:
        result = await self._session.execute(
            select(LabeledVacancy.verdict, func.count()).group_by(LabeledVacancy.verdict)
        )
        by_verdict: dict[str, int] = {verdict: count for verdict, count in result.all()}
        return by_verdict.get("relevant", 0), by_verdict.get("irrelevant", 0)

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


class InboxMessageRepository:
    """Реализация InboxMessageRepositoryPort + выборка секций (этап 2)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_processed(self, gmail_id: str) -> bool:
        result = await self._session.execute(
            select(InboxMessageRow.id).where(InboxMessageRow.gmail_id == gmail_id)
        )
        return result.first() is not None

    async def add(self, gmail_id: str, message: InboxMessageDTO) -> None:
        stmt = (
            insert(InboxMessageRow)
            .values(
                gmail_id=gmail_id,
                source=message.source,
                sender=message.sender,
                subject=message.subject,
                summary=message.summary,
                url=message.url,
                section=message.section,
                received_at=message.received_at,
            )
            .on_conflict_do_nothing(index_elements=["gmail_id"])
        )
        await self._session.execute(stmt)

    async def sections_since(self, since: datetime) -> dict[str, list[InboxMessageDTO]]:
        result = await self._session.execute(
            select(InboxMessageRow)
            .where(InboxMessageRow.received_at >= since)
            .where(InboxMessageRow.section.in_(["mail", "linkedin"]))
            .order_by(InboxMessageRow.received_at.desc())
        )
        sections: dict[str, list[InboxMessageDTO]] = {"mail": [], "linkedin": []}
        for row in result.scalars():
            sections[row.section].append(
                InboxMessageDTO(
                    source=row.source,
                    sender=row.sender,
                    subject=row.subject,
                    summary=row.summary,
                    url=row.url,
                    received_at=row.received_at,
                    section=row.section,
                )
            )
        return sections


class ScraperApprovalRepository:
    """Реализация ScraperApprovalPort (scraper_approval, этап 5)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_approved(self, site: str) -> bool:
        result = await self._session.execute(
            select(ScraperApproval.site_name).where(ScraperApproval.site_name == site)
        )
        return result.first() is not None

    async def approve(self, site: str, chat_id: int) -> None:
        """Идемпотентно (S1-подобно): повторный approve не меняет approved_at."""
        stmt = (
            insert(ScraperApproval)
            .values(site_name=site, approved_by_chat_id=chat_id)
            .on_conflict_do_nothing(index_elements=["site_name"])
        )
        await self._session.execute(stmt)

    async def approved_sites(self) -> set[str]:
        result = await self._session.execute(select(ScraperApproval.site_name))
        return {row for row in result.scalars()}


class InviteRepository:
    """Реализация InviteRepositoryPort (linkedin_target, этап 3)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_pairs(self) -> set[tuple[str, str]]:
        result = await self._session.execute(
            select(LinkedInTarget.company, LinkedInTarget.title).where(
                LinkedInTarget.status != "accepted"
            )
        )
        return {(row.company, row.title) for row in result}

    async def add(self, draft: InviteDraftDTO) -> int:
        row = LinkedInTarget(
            title=draft.title,
            company=draft.company,
            search_url=draft.search_url,
            invite_text=draft.invite_text,
            status=str(draft.status),
        )
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def get(self, invite_id: int) -> InviteDraftDTO | None:
        row = await self._session.get(LinkedInTarget, invite_id)
        return self._to_domain(row) if row else None

    async def save(self, invite_id: int, draft: InviteDraftDTO) -> None:
        await self._session.execute(
            update(LinkedInTarget)
            .where(LinkedInTarget.id == invite_id)
            .values(status=str(draft.status), sent_at=draft.sent_at, accepted_at=draft.accepted_at)
        )

    async def pending(self) -> list[tuple[int, InviteDraftDTO]]:
        result = await self._session.execute(
            select(LinkedInTarget)
            .where(LinkedInTarget.status == "proposed")
            .order_by(LinkedInTarget.created_at.asc())
        )
        return [(row.id, self._to_domain(row)) for row in result.scalars()]

    async def pending_older_than(self, days: int) -> list[tuple[int, InviteDraftDTO]]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self._session.execute(
            select(LinkedInTarget)
            .where(LinkedInTarget.status == "proposed")
            .where(LinkedInTarget.created_at < cutoff)
        )
        return [(row.id, self._to_domain(row)) for row in result.scalars()]

    async def counts(self) -> dict[str, int]:
        result = await self._session.execute(
            select(LinkedInTarget.status, func.count()).group_by(LinkedInTarget.status)
        )
        return {row[0]: row[1] for row in result}

    @staticmethod
    def _to_domain(row: LinkedInTarget) -> InviteDraftDTO:
        return InviteDraftDTO(
            title=row.title,
            company=row.company,
            search_url=row.search_url,
            invite_text=row.invite_text,
            status=InviteStatus(row.status),
            sent_at=row.sent_at,
            accepted_at=row.accepted_at,
        )
