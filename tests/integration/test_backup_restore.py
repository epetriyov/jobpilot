"""[X-I2] backup.sh создаёт дамп; restore на чистую БД проходит; счётчики строк совпадают."""

import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
BACKUP_SH = ROOT / "deploy" / "backup.sh"


def _row_count(url: str) -> int:
    engine = create_engine(url)
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM job_run")).scalar_one()


def test_backup_then_restore_preserves_rows(pg_url: str, alembic_config, tmp_path: Path) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job_run (job_name, status, trace_id, started_at) "
                "VALUES ('smoke','success','t1', now()), ('smoke','error','t2', now())"
            )
        )
    before = _row_count(pg_url)
    assert before == 2

    # Режим фиксируем явно: тестовая БД — testcontainer, а не compose-сервис db;
    # auto-режим мог бы уйти в запущенный compose-стек и дампить не ту БД.
    mode = "direct" if shutil.which("pg_dump") else "client-docker"
    env = {"POSTGRES_DSN": pg_url, "BACKUP_DIR": str(tmp_path), "BACKUP_MODE": mode}
    subprocess.run(["bash", str(BACKUP_SH)], check=True, env={**_os_environ(), **env})
    dumps = list(tmp_path.glob("jobpilot_*.sql.gz"))
    assert len(dumps) == 1

    # чистим БД и восстанавливаем
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run(
        ["bash", str(BACKUP_SH), "restore", str(dumps[0])],
        check=True,
        env={**_os_environ(), **env},
    )

    assert _row_count(pg_url) == before


def _os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)
