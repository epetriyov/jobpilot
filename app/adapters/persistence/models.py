"""SQLAlchemy-модели минимального слоя хранения (DOMAIN.md §4, data-model.md).

Время в БД — UTC (timestamptz). Полное `vacancy`/`application` — этап 6.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SeenVacancy(Base):
    """Реестр виденных вакансий: дедуп S1 (source_ref) и S2 (normalized_key за 30 дней)."""

    __tablename__ = "seen_vacancy"

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
