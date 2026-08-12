"""[T5xx][S-C7/S-C8] Golden парсера VK (team.vk.company) на записанном SSR-payload.

Один честный GET (см. tests/golden/sites/vk/list.html — обезличенный фрагмент
исходной страницы со встроенным __NEXT_DATA__). Парсер извлекает встроенный JSON
списка вакансий — стабильнее, чем CSS-классы вёрстки. Слом структуры ответа →
падение с diff-сигналом «скрейпер vk сломан».
"""

from __future__ import annotations

from app.adapters.sites.vk import parse_vk
from tests.golden.sites.harness import assert_golden, load_expected, load_payload


def test_golden_matches_recorded_payload() -> None:
    vacancies = parse_vk(load_payload("vk", "list.html"))
    assert_golden(vacancies, load_expected("vk", "list.expected.json"))


def test_dedup_by_external_id() -> None:
    """Дубликат id в payload схлопывается (в фикстуре id 52461 встречается дважды)."""
    vacancies = parse_vk(load_payload("vk", "list.html"))
    ids = [v.source_ref.external_id for v in vacancies]
    assert len(ids) == len(set(ids))


def test_mapping_invariants() -> None:
    vacancies = parse_vk(load_payload("vk", "list.html"))
    assert vacancies, "фикстура должна давать вакансии"
    for v in vacancies:
        assert v.source_ref.source == "site"
        assert v.source_ref.site_name == "vk"
        assert v.company == "vk"  # портал = один работодатель (data-model §маппинг)
        assert v.url.startswith("https://team.vk.company/vacancy/")
        assert "utm" not in v.url and "?" not in v.url  # url без трекинга
        assert v.title


def test_empty_payload_returns_empty() -> None:
    assert parse_vk("") == []


def test_html_without_next_data_returns_empty() -> None:
    assert parse_vk("<html><body>no data</body></html>") == []
