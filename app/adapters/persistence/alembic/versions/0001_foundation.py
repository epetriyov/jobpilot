"""foundation: seen_vacancy, labeled_vacancy, llm_call, job_run + pgvector

Revision ID: 0001_foundation
Revises:
Create Date: 2026-07-06

Минимальный слой хранения этапов 0–5 (DOMAIN.md §4). Одна миграция = один этап.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "seen_vacancy",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_ref", sa.Text(), nullable=False, unique=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("normalized_key", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("digest_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_seen_vacancy_normalized_key", "seen_vacancy", ["normalized_key"])

    op.create_table(
        "labeled_vacancy",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("verdict IN ('relevant','irrelevant')", name="ck_labeled_verdict"),
    )

    op.create_table(
        "llm_call",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_llm_call_created_at", "llm_call", ["created_at"])

    op.create_table(
        "job_run",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("items_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','success','partial','error')", name="ck_job_run_status"
        ),
    )
    op.create_index("ix_job_run_started_at", "job_run", ["started_at"])


def downgrade() -> None:
    op.drop_table("job_run")
    op.drop_table("llm_call")
    op.drop_table("labeled_vacancy")
    op.drop_table("seen_vacancy")
