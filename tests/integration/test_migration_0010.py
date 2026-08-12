"""T6E-2: миграция 0010_stage6e — таблица cover_letter (data-model §4).

⚠️ Требует полной цепочки миграций 0007→0010 (фундамент 6A даёт `vacancy`).
В изолированном worktree 6E цепочка ещё не линеаризована — тест зелёный после
интеграции оркестратором. Помечен integration (вне обязательного гейта, без Docker).
"""

import pytest
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration


def test_cover_letter_table_present(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    assert "cover_letter" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("cover_letter")}
    assert {"id", "vacancy_id", "text", "prompt_version", "created_at"} <= columns

    # FK vacancy(id) — письмо привязано к вакансии (6A)
    fks = inspector.get_foreign_keys("cover_letter")
    assert any(fk["referred_table"] == "vacancy" for fk in fks)

    # CHECK длины ≤2000 (M3) — тело письма ограничено на уровне БД
    checks = {c["name"] for c in inspector.get_check_constraints("cover_letter")}
    assert "ck_cover_letter_len" in checks

    indexes = {i["name"] for i in inspector.get_indexes("cover_letter")}
    assert "ix_cover_letter_vacancy_id" in indexes


def test_downgrade_drops_cover_letter(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0007_stage6a_vacancy")

    engine = create_engine(pg_url)
    assert "cover_letter" not in inspect(engine).get_table_names()
