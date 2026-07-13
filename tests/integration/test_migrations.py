"""[F-I1] Чистая БД → alembic upgrade head → все таблицы §4 DOMAIN.md; повтор идемпотентен."""

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {"seen_vacancy", "labeled_vacancy", "llm_call", "job_run"}


def test_upgrade_creates_all_tables(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    tables = set(inspect(engine).get_table_names())
    assert tables >= EXPECTED_TABLES


def test_upgrade_is_idempotent(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    # повторный прогон не должен падать и не плодит изменений
    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version


def test_stage1_columns_present(pg_url: str, alembic_config) -> None:
    """Миграция 0002_stage1: снапшот и скор в seen_vacancy (data-model этапа 1)."""
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    columns = {c["name"] for c in inspect(engine).get_columns("seen_vacancy")}
    assert {"title", "description_text", "score", "prompt_version", "scored_at"} <= columns
    indexes = {i["name"] for i in inspect(engine).get_indexes("seen_vacancy")}
    assert "ix_seen_vacancy_scored" in indexes


def test_stage2_inbox_message_present(pg_url: str, alembic_config) -> None:
    """Миграция 0003_stage2: таблица inbox_message (data-model этапа 2)."""
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    assert "inbox_message" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("inbox_message")}
    assert {"gmail_id", "source", "summary", "section", "received_at"} <= columns
    # тело письма в БД отсутствует по построению (M4)
    assert "body" not in columns and "body_text" not in columns


def test_pgvector_extension_enabled(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert exists == 1
