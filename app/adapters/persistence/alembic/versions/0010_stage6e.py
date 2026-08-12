"""stage6e: cover_letter (specs/006-crm/data-model.md §4)

Revision ID: 0010_stage6e
Revises: 0007_stage6a_vacancy
Create Date: 2026-08-12

Сопроводительные письма под-этапа 6E: несколько версий на вакансию (🔁 добавляет
строку, последняя — актуальная). FK → vacancy(id) (хранилище 6A). CHECK длины ≤2000
дублирует инвариант M3 (COVER_LETTER_MAX_CHARS). Тело письма — данные владельца в
его БД (не лог, M4).

⚠️ down_revision=`0007_stage6a_vacancy` — 6E разрабатывается параллельно ветке CRM
поверх фундамента 6A; при мерже раньше 6B/6D оркестратор линеаризует цепочку
0007→0010 (research §7). Итоговый down_revision может стать `0009_stage6d_pgvector`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_stage6e"
down_revision: str | None = "0009_stage6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cover_letter",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "vacancy_id",
            sa.BigInteger(),
            sa.ForeignKey("vacancy.id"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("char_length(text) <= 2000", name="ck_cover_letter_len"),
    )
    op.create_index("ix_cover_letter_vacancy_id", "cover_letter", ["vacancy_id"])


def downgrade() -> None:
    op.drop_index("ix_cover_letter_vacancy_id", table_name="cover_letter")
    op.drop_table("cover_letter")
