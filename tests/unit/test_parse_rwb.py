"""Golden + деградация чистого парсера RWB (career.rwb.ru) ([S-C7]/[S-C8]).

Транспорт↔парсер (plan.md): parse_rwb тестируется на записанном payload,
независимо от способа добычи. Golden ловит слом структуры ответа; отдельные
кейсы — деградация без исключения (пустой/битый payload, дедуп, маппинг полей).
"""

from __future__ import annotations

import json

import pytest

from app.adapters.sites.rwb import parse_rwb, rwb_factory
from app.config import Settings
from tests.golden.sites.harness import assert_golden, load_expected, load_payload

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test-telegram-token",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "POSTGRES_DSN": "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot",
}


def test_parse_rwb_golden() -> None:
    payload = load_payload("rwb", "vacancies.json")
    expected = load_expected("rwb", "vacancies.expected.json")
    assert_golden(parse_rwb(payload), expected)


def test_parse_rwb_empty_items_returns_empty() -> None:
    assert parse_rwb(json.dumps({"status": 200, "data": {"items": [], "range": {}}})) == []


def test_parse_rwb_missing_data_items_returns_empty() -> None:
    assert parse_rwb(json.dumps({"status": 200, "data": {}})) == []
    assert parse_rwb(json.dumps({"status": 200})) == []


def test_parse_rwb_broken_json_returns_empty() -> None:
    assert parse_rwb("<html>SPA shell</html>") == []
    assert parse_rwb("") == []


def test_parse_rwb_skips_items_without_identity() -> None:
    payload = json.dumps(
        {
            "data": {
                "items": [
                    {"name": "Без id", "city_title": "Москва"},
                    {"id": 42},  # без name
                    {"id": 7, "name": "Ок", "city_title": "Тула"},
                ]
            }
        }
    )
    result = parse_rwb(payload)
    assert [v.source_ref.external_id for v in result] == ["7"]
    assert result[0].url == "https://career.rwb.ru/vacancies/7"


def test_parse_rwb_dedup_by_external_id() -> None:
    item = {"id": 100, "name": "Дубль", "city_title": "Москва"}
    payload = json.dumps({"data": {"items": [item, dict(item, name="Дубль-2")]}})
    result = parse_rwb(payload)
    assert len(result) == 1
    assert result[0].source_ref.external_id == "100"


def test_parse_rwb_maps_location_and_company() -> None:
    payload = json.dumps(
        {"data": {"items": [{"id": 9, "name": "Пекарь", "city_title": "Коледино"}]}}
    )
    (vac,) = parse_rwb(payload)
    assert vac.company == "rwb"
    assert vac.location == "Коледино"
    assert vac.source_ref.site_name == "rwb"


def test_parse_rwb_description_dedup_join_skips_empties() -> None:
    payload = json.dumps(
        {
            "data": {
                "items": [
                    {
                        "id": 5,
                        "name": "UX",
                        "direction_title": "UX",
                        "direction_role_title": "UX Исследователь",
                        "experience_type_title": "",
                        "employment_types": [
                            {"title": "Офис"},
                            {"title": "Офис"},  # дубль → схлопнуть
                            {"title": ""},  # пусто → пропустить
                            {"title": "Гибрид"},
                        ],
                    }
                ]
            }
        }
    )
    (vac,) = parse_rwb(payload)
    assert vac.raw["description"] == "UX\nUX Исследователь\nОфис\nГибрид"


def test_parse_rwb_missing_location_is_none() -> None:
    payload = json.dumps({"data": {"items": [{"id": 1, "name": "Без города"}]}})
    (vac,) = parse_rwb(payload)
    assert vac.location is None


def test_rwb_factory_builds_site_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    adapter = rwb_factory(Settings.load(env_file=None), None)
    assert adapter.name == "rwb"
