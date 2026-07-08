"""Alembic env: синхронный движок, DSN из окружения (POSTGRES_DSN)."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.adapters.persistence.models import Base

config = context.config
target_metadata = Base.metadata


def _sync_dsn() -> str:
    dsn = os.environ["POSTGRES_DSN"]
    # alembic гоняем на синхронном драйвере
    return dsn.replace("+asyncpg", "").replace("+psycopg_async", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_dsn()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
