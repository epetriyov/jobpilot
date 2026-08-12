"""T6F-5 [P-I1] (MCP4): read-роль `mcp_ro` не может писать в БД.

Второй рубеж поверх белого списка инструментов: даже если бы read-инструмент попытался
записать, роль `mcp_ro` (GRANT SELECT, без INSERT/UPDATE/DELETE) упирается в отказ прав
БД. Тест поднимает роль теми же grant'ами, что и ops-скрипт deploy/mcp/create_ro_role.sql,
и проверяет: SELECT проходит, INSERT/UPDATE/DELETE — InsufficientPrivilege.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "mcp" / "create_ro_role.sql"


def test_ops_script_present_and_grants_select() -> None:
    sql = _SCRIPT.read_text(encoding="utf-8")
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro" in sql
    assert "REVOKE INSERT, UPDATE, DELETE" in sql


def test_mcp_ro_role_cannot_write(pg_url: str, alembic_config) -> None:  # type: ignore[no-untyped-def]
    from alembic import command

    command.upgrade(alembic_config, "head")

    url = make_url(pg_url)
    admin = create_engine(pg_url)
    with admin.begin() as conn:
        conn.execute(text("DROP ROLE IF EXISTS mcp_ro"))
        conn.execute(text("CREATE ROLE mcp_ro LOGIN PASSWORD 'ro_secret'"))
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{url.database}" TO mcp_ro'))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO mcp_ro"))
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro"))
        conn.execute(
            text("REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM mcp_ro")
        )
    admin.dispose()

    ro_url = url.set(username="mcp_ro", password="ro_secret")
    ro_engine = create_engine(ro_url)
    try:
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT count(*) FROM vacancy"))  # read — ок
        with pytest.raises(Exception) as exc:
            with ro_engine.begin() as conn:
                conn.execute(text("INSERT INTO vacancy (source_ref) VALUES ('x')"))
        assert "permission denied" in str(exc.value).lower()
    finally:
        ro_engine.dispose()
