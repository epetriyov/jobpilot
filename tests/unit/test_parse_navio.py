"""Golden + деградация чистого парсера Navio ([S-C7]/[S-C8]).

Транспорт↔парсер (plan.md): parse_navio тестируется на записанном payload
(реальный Gatsby-`window.pageData`), независимо от способа добычи. Golden ловит
слом структуры ответа; отдельные кейсы — деградация без исключения
(пустой/битый payload, пропуск карточек без id/title, дедуп).
"""

from __future__ import annotations

import json

import pytest

from app.adapters.sites.navio import navio_factory, parse_navio
from app.config import Settings
from tests.golden.sites.harness import assert_golden, load_expected, load_payload

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test-telegram-token",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "POSTGRES_DSN": "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot",
}


def _page(vacancies: list[dict[str, object]]) -> str:
    """Собрать минимальный Gatsby-HTML с window.pageData вокруг vacancies."""
    data = {"result": {"serverData": {"vacancies": vacancies}}}
    return (
        '<html><body><script id="gatsby-script-loader">/*<![CDATA[*/'
        "window.pageData=" + json.dumps(data, ensure_ascii=False) + ";"
        "/*]]>*/</script></body></html>"
    )


def test_parse_navio_golden() -> None:
    payload = load_payload("navio", "list.html")
    expected = load_expected("navio", "list.expected.json")
    assert_golden(parse_navio(payload), expected)


def test_parse_navio_empty_payload_returns_empty() -> None:
    assert parse_navio("") == []
    assert parse_navio("   ") == []


def test_parse_navio_garbled_html_returns_empty() -> None:
    assert parse_navio("<html>anti-bot wall</html>") == []
    assert parse_navio("<script>window.pageData={ broken</script>") == []


def test_parse_navio_no_vacancies_returns_empty() -> None:
    assert parse_navio(_page([])) == []


def test_parse_navio_skips_cards_without_identity() -> None:
    payload = _page(
        [
            {"title": "Без id", "city": {"text": "Москва"}},  # нет id
            {"id": "42"},  # нет title
            {"id": "7", "title": "Ок", "city": {"text": "Тула"}, "jobType": {"text": "Офис"}},
        ]
    )
    result = parse_navio(payload)
    assert [v.source_ref.external_id for v in result] == ["7"]
    assert result[0].url == "https://navio.auto/vacancies/7"
    assert result[0].company == "navio"
    assert result[0].location == "Тула, Офис"


def test_parse_navio_dedup_by_id() -> None:
    card = {"id": "100", "title": "Дубль", "city": {"text": "Москва"}}
    payload = _page([card, dict(card, title="Дубль-2")])
    result = parse_navio(payload)
    assert len(result) == 1
    assert result[0].source_ref.external_id == "100"


def test_parse_navio_location_absent_when_no_city() -> None:
    payload = _page([{"id": "9", "title": "Без города"}])
    result = parse_navio(payload)
    assert result[0].location is None


def test_navio_factory_builds_site_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    adapter = navio_factory(Settings.load(env_file=None), None)
    assert adapter.name == "navio"
