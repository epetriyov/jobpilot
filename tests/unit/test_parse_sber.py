"""Golden + деградация чистого парсера Сбера ([S-C7]/[S-C8]).

Транспорт↔парсер (plan.md): parse_sber тестируется на записанном payload,
независимо от способа добычи. Golden ловит слом структуры ответа; отдельные
кейсы — деградация без исключения (пустой/битый payload, дедуп).
"""

from __future__ import annotations

import json

import pytest

from app.adapters.sites.sber import parse_sber, sber_factory
from app.config import Settings
from tests.golden.sites.harness import assert_golden, load_expected, load_payload

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test-telegram-token",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "POSTGRES_DSN": "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot",
}


def test_parse_sber_golden() -> None:
    payload = load_payload("sber", "publications.json")
    expected = load_expected("sber", "publications.expected.json")
    assert_golden(parse_sber(payload), expected)


def test_parse_sber_empty_vacancies_returns_empty() -> None:
    assert parse_sber(json.dumps({"success": True, "data": {"vacancies": [], "total": 0}})) == []


def test_parse_sber_missing_data_key_returns_empty() -> None:
    assert parse_sber(json.dumps({"success": True})) == []


def test_parse_sber_broken_json_returns_empty() -> None:
    assert parse_sber("<html>anti-bot wall</html>") == []
    assert parse_sber("") == []


def test_parse_sber_skips_cards_without_identity() -> None:
    payload = json.dumps(
        {
            "data": {
                "vacancies": [
                    {"title": "Без internalId", "publicationId": "x", "city": "г Москва"},
                    {"internalId": 42, "publicationId": "y"},  # без title
                    {"internalId": 7, "title": "Ок", "publicationId": "z", "city": "г Тула"},
                ]
            }
        }
    )
    result = parse_sber(payload)
    assert [v.source_ref.external_id for v in result] == ["z"]
    assert result[0].url == "https://rabota.sber.ru/search/7/"


def test_parse_sber_dedup_by_publication_id() -> None:
    card = {
        "internalId": 100,
        "title": "Дубль",
        "publicationId": "dup-1",
        "city": "г Москва",
    }
    payload = json.dumps({"data": {"vacancies": [card, dict(card, internalId=101)]}})
    result = parse_sber(payload)
    assert len(result) == 1
    assert result[0].source_ref.external_id == "dup-1"


def test_parse_sber_external_id_falls_back_to_internal_id() -> None:
    payload = json.dumps(
        {"data": {"vacancies": [{"internalId": 555, "title": "Без publicationId"}]}}
    )
    result = parse_sber(payload)
    assert result[0].source_ref.external_id == "555"


def test_sber_factory_builds_site_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    adapter = sber_factory(Settings.load(env_file=None), None)
    assert adapter.name == "sber"
