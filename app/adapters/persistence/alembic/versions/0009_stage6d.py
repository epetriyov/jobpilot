"""stage6d: HNSW-индекс на labeled_vacancy.embedding (specs/006-crm/data-model.md §3)

Revision ID: 0009_stage6d
Revises: 0006_stage5
Create Date: 2026-08-12

Семантический few-shot (pgvector): колонка `labeled_vacancy.embedding vector(768)`
существует с 0001; здесь добавляется только индекс близости. HNSW + cosine —
малый объём размеченных, без обучения списков (research §3). Наполнение эмбеддингов —
идемпотентный backfill-джоб (LLM-вызовы в миграции запрещены).

⚠️ ИНТЕГРАЦИЯ (оркестратору): целевой `down_revision` этой миграции —
`0007_stage6a_vacancy` (data-model §7; при мерже раньше 6B — иначе
`0008_stage6b_application`). В изолированном worktree 6D эти ревизии ещё
отсутствуют, поэтому цепочка временно замкнута на фактический head `0006_stage5`,
чтобы гейты (`alembic upgrade head`) были зелёными. При линеаризации на мерже —
поправить `down_revision` на фактического предшественника (индекс/логику не трогать).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_stage6d"
# TODO(integration): rebase → "0007_stage6a_vacancy" (см. docstring выше)
down_revision: str | None = "0008_stage6b_application"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_labeled_embedding_hnsw"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
        "ON labeled_vacancy USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
