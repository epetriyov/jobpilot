"""[F-I1] Миграция 0007_stage6a_vacancy: rename seen_vacancy→vacancy + backfill.

Данные историков не теряются: count сохранён, id/source_ref/content_hash/
normalized_key/скор/снапшот целы; `raw` бэкфилл-нут из description_text;
уникальность source_ref (S1) держится; upgrade идемпотентен; downgrade→upgrade
данные целы. Стратегия — research §1, data-model §1.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

_PRE_REVISION = "0006_stage5"
_REVISION = "0007_stage6a_vacancy"

# 3 историка в seen_vacancy: row-1 полный снапшот+скор, row-2 без скора,
# row-3 без description_text (backfill оставляет raw='{}').
_SEEN_ROWS = [
    {
        "source_ref": "hh:111",
        "content_hash": "hash-111",
        "normalized_key": "acme|engineering manager",
        "title": "Engineering Manager",
        "company": "Acme",
        "url": "https://hh.ru/vacancy/111",
        "description_text": "Руководство командой из 8 инженеров.",
        "score": 82,
        "score_reason": "сильный матч",
        "prompt_version": "scoring/1",
        "score_model": "fake/model",
    },
    {
        "source_ref": "site:vk:222",
        "content_hash": "hash-222",
        "normalized_key": "globex|team lead",
        "title": "Team Lead",
        "company": "Globex",
        "url": "https://vk.company/222",
        "description_text": "Лид команды платформы.",
        "score": None,
        "score_reason": None,
        "prompt_version": None,
        "score_model": None,
    },
    {
        "source_ref": "hh:333",
        "content_hash": "hash-333",
        "normalized_key": "initech|head of engineering",
        "title": "Head of Engineering",
        "company": "Initech",
        "url": "https://hh.ru/vacancy/333",
        "description_text": None,
        "score": None,
        "score_reason": None,
        "prompt_version": None,
        "score_model": None,
    },
]

_LABELED_ROWS = [
    {
        "source_ref": "hh:111",
        "title": "Engineering Manager",
        "company": "Acme",
        "url": "https://hh.ru/vacancy/111",
        "description_text": "Руководство командой из 8 инженеров.",
        "verdict": "relevant",
    },
    {
        "source_ref": "site:vk:222",
        "title": "Team Lead",
        "company": "Globex",
        "url": "https://vk.company/222",
        "description_text": "Лид команды платформы.",
        "verdict": "irrelevant",
    },
]


def _seed_seen(engine) -> None:  # type: ignore[no-untyped-def]
    insert_seen = text(
        "INSERT INTO seen_vacancy (source_ref, content_hash, normalized_key, first_seen_at, "
        "title, company, url, description_text, salary_from, salary_to, salary_currency, "
        "score, score_reason, prompt_version, score_model) VALUES ("
        ":source_ref, :content_hash, :normalized_key, now(), :title, :company, :url, "
        ":description_text, 300000, NULL, 'RUR', :score, :score_reason, :prompt_version, "
        ":score_model)"
    )
    insert_labeled = text(
        "INSERT INTO labeled_vacancy (source_ref, title, company, url, description_text, verdict) "
        "VALUES (:source_ref, :title, :company, :url, :description_text, :verdict)"
    )
    with engine.begin() as conn:
        for row in _SEEN_ROWS:
            conn.execute(insert_seen, row)
        for row in _LABELED_ROWS:
            conn.execute(insert_labeled, row)


def test_migration_0007_backfills_and_preserves_data(pg_url: str, alembic_config) -> None:
    from alembic import command

    # 1. Доводим схему до состояния «до 0007» и наполняем историками.
    command.upgrade(alembic_config, _PRE_REVISION)
    engine = create_engine(pg_url)
    _seed_seen(engine)

    # 2. Прогоняем целевую миграцию.
    command.upgrade(alembic_config, _REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "vacancy" in tables
    assert "seen_vacancy" not in tables  # rename, не копия

    columns = {c["name"] for c in inspector.get_columns("vacancy")}
    assert {"raw", "duplicate_of", "canary"} <= columns
    # снапшот/скор-колонки переехали с таблицей
    assert {"source_ref", "content_hash", "normalized_key", "score", "description_text"} <= columns

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM vacancy")).scalar_one() == len(_SEEN_ROWS)
        assert conn.execute(text("SELECT count(*) FROM labeled_vacancy")).scalar_one() == len(
            _LABELED_ROWS
        )

        # id сохранён и стабилен (на него сошлётся application.vacancy_id).
        ids = conn.execute(text("SELECT source_ref, id FROM vacancy")).all()
        assert all(vid is not None for _, vid in ids)

        # Полный историк цел.
        r1 = (
            conn.execute(
                text(
                    "SELECT content_hash, normalized_key, score, score_reason, prompt_version, "
                    "score_model, title, description_text, canary, duplicate_of, "
                    "raw->>'description' AS raw_desc FROM vacancy WHERE source_ref = 'hh:111'"
                )
            )
            .mappings()
            .one()
        )
        assert r1["content_hash"] == "hash-111"
        assert r1["normalized_key"] == "acme|engineering manager"
        assert r1["score"] == 82  # R1 сохранён
        assert r1["prompt_version"] == "scoring/1"
        assert r1["title"] == "Engineering Manager"
        assert r1["canary"] is False
        assert r1["duplicate_of"] is None
        assert r1["raw_desc"] == "Руководство командой из 8 инженеров."  # backfill

        # Историк без description_text → raw остался пустым объектом.
        r3 = (
            conn.execute(
                text("SELECT raw, description_text FROM vacancy WHERE source_ref = 'hh:333'")
            )
            .mappings()
            .one()
        )
        assert r3["description_text"] is None
        assert r3["raw"] == {}

    # 3. S1: уникальность source_ref держится на новой таблице.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO vacancy (source_ref, content_hash, normalized_key, first_seen_at) "
                    "VALUES ('hh:111', 'dup', 'dup|dup', now())"
                )
            )

    # 4. Повторный upgrade идемпотентен (alembic не переигрывает уже применённое).
    command.upgrade(alembic_config, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM vacancy")).scalar_one() == len(_SEEN_ROWS)


def test_migration_0007_downgrade_upgrade_roundtrip(pg_url: str, alembic_config) -> None:
    from alembic import command

    command.upgrade(alembic_config, _PRE_REVISION)
    engine = create_engine(pg_url)
    _seed_seen(engine)
    command.upgrade(alembic_config, _REVISION)

    # downgrade возвращает таблицу seen_vacancy без additive-колонок, данные целы.
    command.downgrade(alembic_config, _PRE_REVISION)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "seen_vacancy" in tables
    assert "vacancy" not in tables
    columns = {c["name"] for c in inspector.get_columns("seen_vacancy")}
    assert {"raw", "duplicate_of", "canary"}.isdisjoint(columns)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM seen_vacancy")).scalar_one() == len(
            _SEEN_ROWS
        )
        assert (
            conn.execute(
                text("SELECT score FROM seen_vacancy WHERE source_ref = 'hh:111'")
            ).scalar_one()
            == 82
        )

    # upgrade снова — данные по-прежнему целы (id и скор сохранены).
    command.upgrade(alembic_config, _REVISION)
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT score, raw->>'description' AS d FROM vacancy "
                    "WHERE source_ref = 'hh:111'"
                )
            )
            .mappings()
            .one()
        )
        assert row["score"] == 82
        assert row["d"] == "Руководство командой из 8 инженеров."
