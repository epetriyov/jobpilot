"""stage6b: application + interview_round (specs/006-crm/data-model.md §2)

Revision ID: 0008_stage6b_application
Revises: 0007_stage6a_vacancy
Create Date: 2026-08-12

CRM-агрегат Application (§3.3): один активный на вакансию — C1 (unique vacancy_id,
удаление = DELETE строки). CHECK на статусы/этапы отказа; rejected требует stage.
Дочерняя interview_round: FK CASCADE, монотонность (uq ordinal, uq kind) — C2.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_stage6b_application"
down_revision: str | None = "0007_stage6a_vacancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reject_stage", sa.String(16)),
        sa.Column("interview_url", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancy.id"], name="fk_application_vacancy"),
        sa.UniqueConstraint("vacancy_id", name="uq_application_vacancy"),
        sa.CheckConstraint(
            "status IN ('new','applied','interview','offer','rejected')",
            name="ck_application_status",
        ),
        sa.CheckConstraint(
            "reject_stage IS NULL OR reject_stage IN ('pre_hr','hr','tech','final')",
            name="ck_application_reject_stage",
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR reject_stage IS NOT NULL",
            name="ck_application_rejected_has_stage",
        ),
    )
    op.create_table(
        "interview_round",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["application.id"],
            name="fk_interview_round_app",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("application_id", "ordinal", name="uq_interview_round_ordinal"),
        sa.UniqueConstraint("application_id", "kind", name="uq_interview_round_kind"),
    )


def downgrade() -> None:
    op.drop_table("interview_round")
    op.drop_table("application")
