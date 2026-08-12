"""SQLAlchemy-модели минимального слоя хранения (DOMAIN.md §4, data-model.md).

Время в БД — UTC (timestamptz). Полное `vacancy`/`application` — этап 6.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Vacancy(Base):
    """Полное хранилище вакансий (таблица `vacancy`, миграция 0007_stage6a).

    Суперсет реестра виденных: дедуп S1 (source_ref) / S2 (normalized_key за
    30 дней), скор R1, снапшот/raw S3. На `id` ссылается `application.vacancy_id`.
    """

    __tablename__ = "vacancy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_ref: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # этап 1 (0002_stage1): снапшот для карточек/разметки + скор для R1
    title: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    salary_from: Mapped[int | None] = mapped_column(Integer)
    salary_to: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    score_reason: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    score_model: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # этап 6A (0007_stage6a): полное хранилище
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    duplicate_of: Mapped[str | None] = mapped_column(Text)  # SourceRef оригинала (S2)
    canary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class LabeledVacancy(Base):
    """Снапшоты размеченных 👍/👎 — топливо few-shot и eval."""

    __tablename__ = "labeled_vacancy"
    __table_args__ = (
        CheckConstraint("verdict IN ('relevant','irrelevant')", name="ck_labeled_verdict"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))  # заполняется с этапа 6
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LlmCall(Base):
    """Учёт LLM-вызовов (инвариант O1)."""

    __tablename__ = "llm_call"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JobRun(Base):
    """Журнал плановых прогонов (DOMAIN.md §3.6, [F-I3])."""

    __tablename__ = "job_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','success','partial','error')", name="ck_job_run_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    items_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InboxMessageRow(Base):
    """Входящее письмо (этап 2): метаданные + summary; тело письма не хранится (M4)."""

    __tablename__ = "inbox_message"
    __table_args__ = (
        CheckConstraint("source IN ('gmail','linkedin_gmail','hh')", name="ck_inbox_source"),
        CheckConstraint("section IN ('mail','linkedin','hidden')", name="ck_inbox_section"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gmail_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScraperApproval(Base):
    """Одобрение сайта-скрейпера владельцем (`/approve_scraper`, этап 5).

    Служебный флаг источника (не доменный агрегат): наличие строки → сайт в
    основном потоке дайджеста; нет строки → секция «На проверку (canary)».
    """

    __tablename__ = "scraper_approval"

    site_name: Mapped[str] = mapped_column(Text, primary_key=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CoverLetterRow(Base):
    """Сопроводительное письмо (этап 6E): версии на вакансию, последняя — актуальная.

    Тело письма — данные владельца в его БД (нужно для 🔁/✏️ и истории), не лог (M4).
    """

    __tablename__ = "cover_letter"
    __table_args__ = (CheckConstraint("char_length(text) <= 2000", name="ck_cover_letter_len"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vacancy.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LinkedInTarget(Base):
    """Заготовка инвайта (этап 3): роль+компания+ссылка+текст; ПД адресата нет (N1)."""

    __tablename__ = "linkedin_target"
    __table_args__ = (
        CheckConstraint("status IN ('proposed','sent','accepted')", name="ck_invite_status"),
        CheckConstraint("char_length(invite_text) <= 300", name="ck_invite_text_len"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    search_url: Mapped[str] = mapped_column(Text, nullable=False)
    invite_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationRow(Base):
    """Заявка CRM (этап 6B, миграция 0008): статусная машина §3.3, C1 (uq vacancy_id)."""

    __tablename__ = "application"
    __table_args__ = (
        UniqueConstraint("vacancy_id", name="uq_application_vacancy"),
        CheckConstraint(
            "status IN ('new','applied','interview','offer','rejected')",
            name="ck_application_status",
        ),
        CheckConstraint(
            "reject_stage IS NULL OR reject_stage IN ('pre_hr','hr','tech','final')",
            name="ck_application_reject_stage",
        ),
        CheckConstraint(
            "status <> 'rejected' OR reject_stage IS NOT NULL",
            name="ck_application_rejected_has_stage",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("vacancy.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reject_stage: Mapped[str | None] = mapped_column(String(16))
    interview_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InterviewRoundRow(Base):
    """Раунд собеседования (этап 6B, миграция 0008): монотонность в пределах заявки (C2)."""

    __tablename__ = "interview_round"
    __table_args__ = (
        UniqueConstraint("application_id", "ordinal", name="uq_interview_round_ordinal"),
        UniqueConstraint("application_id", "kind", name="uq_interview_round_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("application.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
