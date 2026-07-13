"""stage1: снапшот и скор в seen_vacancy (specs/001-hh-digest/data-model.md)

Revision ID: 0002_stage1
Revises: 0001_foundation
Create Date: 2026-07-08

Минимальный слой не расширяется новой сущностью: seen_vacancy получает
рабочие поля этапа (снапшот для карточек/разметки + скор для R1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0002_stage1"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COLUMNS: list[sa.Column[Any]] = [
    sa.Column("title", sa.Text(), nullable=True),
    sa.Column("company", sa.Text(), nullable=True),
    sa.Column("url", sa.Text(), nullable=True),
    sa.Column("description_text", sa.Text(), nullable=True),
    sa.Column("salary_from", sa.Integer(), nullable=True),
    sa.Column("salary_to", sa.Integer(), nullable=True),
    sa.Column("salary_currency", sa.Text(), nullable=True),
    sa.Column("score", sa.Integer(), nullable=True),
    sa.Column("score_reason", sa.Text(), nullable=True),
    sa.Column("prompt_version", sa.Text(), nullable=True),
    sa.Column("score_model", sa.Text(), nullable=True),
    sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
]


def upgrade() -> None:
    for column in _NEW_COLUMNS:
        op.add_column("seen_vacancy", column)
    op.create_index("ix_seen_vacancy_scored", "seen_vacancy", ["prompt_version", "score"])


def downgrade() -> None:
    op.drop_index("ix_seen_vacancy_scored", table_name="seen_vacancy")
    for column in reversed(_NEW_COLUMNS):
        op.drop_column("seen_vacancy", column.name)
