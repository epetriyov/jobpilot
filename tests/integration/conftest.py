"""Фикстуры интеграционных тестов: реальный Postgres+pgvector через testcontainers.

Требуют Docker; в CI — отдельная джоба. Локально без Docker тесты помечены
`integration` и скипаются (`make test-unit`).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def pg_container() -> Iterator[object]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg16", driver="psycopg") as container:
        yield container


@pytest.fixture()
def pg_url(pg_container: object) -> str:
    # синхронный URL для inspect/psql в тестах миграций
    return pg_container.get_connection_url()  # type: ignore[attr-defined]


@pytest.fixture()
def async_pg_url(pg_url: str) -> str:
    return pg_url.replace("+psycopg", "+psycopg")  # psycopg3 поддерживает async


@pytest.fixture()
def alembic_config(pg_url: str, monkeypatch: pytest.MonkeyPatch):
    """Свежая БД + Alembic config, нацеленный на контейнер."""
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    # чистим схему перед каждым тестом миграций
    engine = create_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    monkeypatch.setenv("POSTGRES_DSN", pg_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "app/adapters/persistence/alembic")
    return cfg


@pytest.fixture()
async def db_session(async_pg_url: str, alembic_config):
    """Мигрированная БД + async-сессия."""
    from alembic import command

    from app.adapters.persistence.database import make_engine, make_session_factory

    command.upgrade(alembic_config, "head")

    engine = make_engine(async_pg_url)
    factory = make_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()
