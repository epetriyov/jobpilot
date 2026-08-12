"""[T6D-2] Миграция 0009_stage6d: HNSW-индекс на labeled_vacancy.embedding.

Проверяет наличие индекса `ix_labeled_embedding_hnsw` (hnsw, vector_cosine_ops)
после upgrade, идемпотентность повторного upgrade и снятие индекса при downgrade.
"""

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

INDEX_NAME = "ix_labeled_embedding_hnsw"


def _index_meta(pg_url: str) -> tuple[str, str] | None:
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT am.amname, pg_get_indexdef(i.indexrelid) "
                "FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "JOIN pg_am am ON am.oid = c.relam "
                "WHERE c.relname = :name"
            ),
            {"name": INDEX_NAME},
        ).first()
    engine.dispose()
    return (row[0], row[1]) if row else None


def test_hnsw_index_present_after_upgrade(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")

    meta = _index_meta(pg_url)
    assert meta is not None, "HNSW-индекс не создан"
    access_method, indexdef = meta
    assert access_method == "hnsw"
    assert "vector_cosine_ops" in indexdef


def test_upgrade_is_idempotent(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")
    assert _index_meta(pg_url) is not None


def test_downgrade_drops_index(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    assert _index_meta(pg_url) is not None

    command.downgrade(alembic_config, "-1")
    assert _index_meta(pg_url) is None
