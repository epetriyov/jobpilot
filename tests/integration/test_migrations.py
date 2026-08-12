"""[F-I1] Чистая БД → alembic upgrade head → все таблицы §4 DOMAIN.md; повтор идемпотентен."""

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {"vacancy", "labeled_vacancy", "llm_call", "job_run"}


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
    """Стейдж-1 снапшот/скор переехали в `vacancy` (rename 0007_stage6a)."""
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    columns = {c["name"] for c in inspect(engine).get_columns("vacancy")}
    assert {"title", "description_text", "score", "prompt_version", "scored_at"} <= columns
    indexes = {i["name"] for i in inspect(engine).get_indexes("vacancy")}
    assert "ix_vacancy_scored" in indexes


def test_stage6a_vacancy_columns_present(pg_url: str, alembic_config) -> None:
    """Миграция 0007_stage6a: seen_vacancy→vacancy + raw/duplicate_of/canary (data-model §1)."""
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "vacancy" in tables
    assert "seen_vacancy" not in tables
    columns = {c["name"] for c in inspector.get_columns("vacancy")}
    assert {"raw", "duplicate_of", "canary"} <= columns
    indexes = {i["name"] for i in inspector.get_indexes("vacancy")}
    assert "ix_vacancy_normalized_key" in indexes  # S2 переехал


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


def test_stage3_linkedin_target_present(pg_url: str, alembic_config) -> None:
    """Миграция 0004_stage3: linkedin_target + частичный уникальный индекс."""
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    assert "linkedin_target" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("linkedin_target")}
    assert {"title", "company", "search_url", "invite_text", "status", "sent_at"} <= columns
    indexes = {i["name"] for i in inspector.get_indexes("linkedin_target")}
    assert "uq_linkedin_target_active" in indexes


def test_stage5_scraper_approval_present(pg_url: str, alembic_config) -> None:
    """Миграция 0006_stage5: таблица scraper_approval (data-model.md этапа 5)."""
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    assert "scraper_approval" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("scraper_approval")}
    assert {"site_name", "approved_at", "approved_by_chat_id"} <= columns
    pk = inspector.get_pk_constraint("scraper_approval")
    assert pk["constrained_columns"] == ["site_name"]


def test_pgvector_extension_enabled(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert exists == 1
