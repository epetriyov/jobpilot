"""stage3: linkedin_target (specs/003-linkedin-invites/data-model.md)

Revision ID: 0004_stage3
Revises: 0003_stage2
Create Date: 2026-07-13

Заготовки инвайтов: роль+компания+ссылка+текст+статус. ПД адресатов нет (N1).
Частичный уникальный индекс — дедуп еженедельных запусков до accepted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_stage3"
down_revision: str | None = "0003_stage2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "linkedin_target",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("search_url", sa.Text(), nullable=False),
        sa.Column("invite_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('proposed','sent','accepted')", name="ck_invite_status"),
        sa.CheckConstraint("char_length(invite_text) <= 300", name="ck_invite_text_len"),
    )
    op.create_index(
        "uq_linkedin_target_active",
        "linkedin_target",
        ["company", "title"],
        unique=True,
        postgresql_where=sa.text("status <> 'accepted'"),
    )


def downgrade() -> None:
    op.drop_index("uq_linkedin_target_active", table_name="linkedin_target")
    op.drop_table("linkedin_target")
