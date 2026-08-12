"""stage6a: seen_vacancy → vacancy (полное хранилище) + raw/duplicate_of/canary

Revision ID: 0007_stage6a_vacancy
Revises: 0006_stage5
Create Date: 2026-08-12

Фундамент этапа 6 (research §1, data-model §1). `seen_vacancy` — суперсет
рабочих полей `vacancy`; переименовываем таблицу (id сохраняется — на него
сошлётся `application.vacancy_id`), добавляем `raw jsonb`, `duplicate_of`,
`canary`, бэкфиллим `raw` историков из `description_text`. Индексы (uq
source_ref — S1, normalized_key — S2, scored — R1) переезжают с таблицей;
для консистентности с ORM переименованы в ix_vacancy_*.

Данные не теряются (rename сохраняет строки и id); инварианты S1/S2/R1/S3
держатся теми же колонками и индексами. [F-I1].
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_stage6a_vacancy"
down_revision: str | None = "0006_stage5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("seen_vacancy", "vacancy")
    op.execute("ALTER INDEX ix_seen_vacancy_normalized_key RENAME TO ix_vacancy_normalized_key")
    op.execute("ALTER INDEX ix_seen_vacancy_scored RENAME TO ix_vacancy_scored")

    op.add_column(
        "vacancy",
        sa.Column(
            "raw",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("vacancy", sa.Column("duplicate_of", sa.Text(), nullable=True))
    op.add_column(
        "vacancy",
        sa.Column("canary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Backfill историков: оригинального HTML для старых строк нет — raw = очищенный
    # текст (S3); строки без description_text остаются с raw='{}'. Новые вакансии
    # пишут полный raw (Vacancy.create).
    op.execute(
        "UPDATE vacancy SET raw = jsonb_build_object('description', description_text) "
        "WHERE description_text IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("vacancy", "canary")
    op.drop_column("vacancy", "duplicate_of")
    op.drop_column("vacancy", "raw")
    op.execute("ALTER INDEX ix_vacancy_scored RENAME TO ix_seen_vacancy_scored")
    op.execute("ALTER INDEX ix_vacancy_normalized_key RENAME TO ix_seen_vacancy_normalized_key")
    op.rename_table("vacancy", "seen_vacancy")
