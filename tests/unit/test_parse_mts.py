"""Golden + деградация чистого парсера МТС ([S-C7]/[S-C8]).

Транспорт↔парсер (plan.md): parse_mts тестируется на записанном JSON-payload
публичного каталога `GET /api/v2/catalog/v1/vacancies`, независимо от способа
добычи. Golden ловит слом структуры ответа; отдельные кейсы — деградация без
исключения (пустой/битый payload, пропуск карточек без id/title, дедуп).
"""

from __future__ import annotations

import json

import pytest

from app.adapters.sites.mts import mts_factory, parse_mts
from app.config import Settings
from tests.golden.sites.harness import assert_golden, load_expected, load_payload

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test-telegram-token",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "POSTGRES_DSN": "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot",
}


def test_parse_mts_golden() -> None:
    payload = load_payload("mts", "vacancies.json")
    expected = load_expected("mts", "vacancies.expected.json")
    assert_golden(parse_mts(payload), expected)


def test_parse_mts_empty_data_returns_empty() -> None:
    assert parse_mts(json.dumps({"data": [], "meta": {}})) == []


def test_parse_mts_missing_data_key_returns_empty() -> None:
    assert parse_mts(json.dumps({"meta": {}})) == []


def test_parse_mts_broken_json_returns_empty() -> None:
    assert parse_mts("<html>anti-bot wall</html>") == []
    assert parse_mts("") == []


def test_parse_mts_skips_cards_without_identity() -> None:
    payload = json.dumps(
        {
            "data": [
                {"title": "Без id", "externalUrl": "https://job.mts.ru/jobs/1"},
                {"id": "abc", "externalUrl": "https://job.mts.ru/jobs/2"},  # без title
                {
                    "id": "keep",
                    "title": "Ок",
                    "externalUrl": "https://job.mts.ru/jobs/3",
                    "cities": [{"title": "Москва"}],
                },
            ]
        }
    )
    result = parse_mts(payload)
    assert [v.source_ref.external_id for v in result] == ["keep"]
    assert result[0].url == "https://job.mts.ru/jobs/3"
    assert result[0].location == "Москва"


def test_parse_mts_dedup_by_id() -> None:
    card = {"id": "dup-1", "title": "Дубль", "externalUrl": "https://job.mts.ru/jobs/9"}
    payload = json.dumps({"data": [card, dict(card, title="Дубль (копия)")]})
    result = parse_mts(payload)
    assert len(result) == 1
    assert result[0].source_ref.external_id == "dup-1"


def test_parse_mts_salary_mapped_when_present() -> None:
    payload = json.dumps(
        {
            "data": [
                {
                    "id": "s1",
                    "title": "С зарплатой",
                    "externalUrl": "https://job.mts.ru/jobs/10",
                    "salary": {"from": 60000, "to": 75000, "currency": "RUB"},
                }
            ]
        }
    )
    v = parse_mts(payload)[0]
    assert (v.salary.from_, v.salary.to, v.salary.currency) == (60000, 75000, "RUB")


def test_parse_mts_multiple_cities_joined() -> None:
    payload = json.dumps(
        {
            "data": [
                {
                    "id": "c1",
                    "title": "Мультигород",
                    "externalUrl": "https://job.mts.ru/jobs/11",
                    "cities": [{"title": "Москва"}, {"title": "Санкт-Петербург"}],
                }
            ]
        }
    )
    assert parse_mts(payload)[0].location == "Москва, Санкт-Петербург"


def test_parse_mts_strips_tracking_from_url() -> None:
    payload = json.dumps(
        {
            "data": [
                {
                    "id": "t1",
                    "title": "С трекингом",
                    "externalUrl": "https://job.mts.ru/jobs/12?utm_source=x&ref=y&foo=bar",
                }
            ]
        }
    )
    assert parse_mts(payload)[0].url == "https://job.mts.ru/jobs/12?foo=bar"


def test_mts_factory_builds_site_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    adapter = mts_factory(Settings.load(env_file=None), None)
    assert adapter.name == "mts"
