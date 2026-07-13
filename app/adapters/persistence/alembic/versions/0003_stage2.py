"""stage2: inbox_message (specs/002-mail-digest/data-model.md)

Revision ID: 0003_stage2
Revises: 0002_stage1
Create Date: 2026-07-13

Метаданные + summary входящих писем; тело письма не хранится (M4-производная).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_stage2"
down_revision: str | None = "0002_stage1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox_message",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("gmail_id", sa.Text(), nullable=False, unique=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("source IN ('gmail','linkedin_gmail','hh')", name="ck_inbox_source"),
        sa.CheckConstraint("section IN ('mail','linkedin','hidden')", name="ck_inbox_section"),
    )
    op.create_index("ix_inbox_message_received_at", "inbox_message", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_inbox_message_received_at", table_name="inbox_message")
    op.drop_table("inbox_message")
