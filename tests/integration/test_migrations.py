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


def test_pgvector_extension_enabled(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert exists == 1
