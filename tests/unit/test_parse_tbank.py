"""[T51x][S-C7]/[S-C8] Golden + unit для parse_tbank (лёгкая волна, JSON POST).

Т-Банк отдаёт список вакансий через POST /pfpjobs/papi/getVacancies (JSON).
parse_tbank — чистая функция над строкой-payload: маппинг карточки портала в
доменный Vacancy (data-model.md §маппинг). Golden доказывает стабильность
проекции; «поплывшая» структура ответа → падение с diff-сигналом «скрейпер сломан».

Источник payload: структура подтверждена (эндпоинт живой, НЕ анти-бот) +
формат карточки URL проверен по career-sitemap (реальные ссылки, HTTP 200).
Тело getVacancies требует валидный `source` из компаньон-вызова — открытый пункт
(см. заметку в app/adapters/sites/tbank.py); golden собран из подтверждённой
структуры, парсер тестируется без сети.
"""

from __future__ import annotations

import json

import pytest

from app.adapters.sites.tbank import parse_tbank
from app.domain.shared import Source
from tests.golden.sites.harness import assert_golden, load_expected, load_payload


def test_golden_matches_recorded_payload() -> None:
    """[S-C8] parse_tbank(payload) сходится с эталонной проекцией."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    assert_golden(vacancies, load_expected("tbank", "vacancies.expected.json"))


def test_maps_source_ref_as_site_tbank() -> None:
    """[S-C7] source=SITE, site_name=tbank, external_id=urlSlug."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    ref = vacancies[0].source_ref
    assert ref.source is Source.SITE
    assert ref.site_name == "tbank"
    assert ref.external_id == "d60eaf9d-656c-48c5-8502-b13fbfa387db"


def test_company_is_portal_name() -> None:
    """Портал = один работодатель: company = имя портала «tbank»."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    assert {v.company for v in vacancies} == {"tbank"}


def test_description_includes_tags() -> None:
    """description_raw = shortDescription + грейд/формат-теги (dict и str)."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    lead = next(v for v in vacancies if v.title == "Руководитель группы разработки")
    assert "Ведущий" in lead.description_text
    assert "Офис" in lead.description_text
    data = next(v for v in vacancies if v.title == "Lead Data Engineer")
    assert "Senior" in data.description_text  # теги-строки тоже попадают


def test_url_has_no_tracking() -> None:
    """URL карточки абсолютный и очищен от query/utm."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    for v in vacancies:
        assert v.url.startswith("https://www.tbank.ru/career/")
        assert "?" not in v.url
        assert "utm" not in v.url


def test_empty_payload_returns_empty() -> None:
    """Пустой список вакансий → []."""
    assert parse_tbank(json.dumps({"resultCode": "OK", "payload": {"vacancies": []}})) == []


def test_missing_payload_key_returns_empty() -> None:
    """Отсутствие payload/vacancies не роняет парсер (S4-совместимо)."""
    assert parse_tbank(json.dumps({"resultCode": "OK"})) == []


def test_dedup_by_external_id() -> None:
    """Повтор urlSlug в ответе → одна карточка (дедуп по external_id)."""
    card = {
        "title": "Тимлид",
        "subtitle": "Москва",
        "category": "IT",
        "shortDescription": "x",
        "salary": None,
        "cities": [],
        "tags": [],
        "urlSlug": "same-uuid",
        "seoSlug": "grp/timlid",
        "source": "it",
    }
    payload = json.dumps({"payload": {"vacancies": [card, dict(card)]}})
    result = parse_tbank(payload)
    assert len(result) == 1


def test_skips_cards_without_required_fields() -> None:
    """Нет urlSlug/title/seoSlug → карточка пропускается (completeness 100%)."""
    payload = json.dumps(
        {
            "payload": {
                "vacancies": [
                    {"title": "Без id", "seoSlug": "grp/x", "urlSlug": ""},
                    {"title": "", "seoSlug": "grp/x", "urlSlug": "u1"},
                    {"title": "Без seo", "seoSlug": "", "urlSlug": "u2"},
                ]
            }
        }
    )
    assert parse_tbank(payload) == []


def test_salary_range_parsed() -> None:
    """«от X до Y ₽» → (X, Y, RUR); «от X ₽» → (X, None, RUR); null → пусто."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    rng = next(v for v in vacancies if v.title == "Тимлид аналитики")
    assert (rng.salary.from_, rng.salary.to, rng.salary.currency) == (250000, 350000, "RUR")
    none_sal = next(v for v in vacancies if v.title == "Head of Engineering")
    assert none_sal.salary.from_ is None
    assert none_sal.salary.currency is None


@pytest.mark.parametrize(
    ("category", "expected_segment"),
    [("IT", "it"), ("BACK_OFFICE", "back-office"), ("service", "service")],
)
def test_category_slug_mapping(category: str, expected_segment: str) -> None:
    """category портала → сегмент URL (ow-map фронта: IT→it, BACK_OFFICE→back-office)."""
    payload = json.dumps(
        {
            "payload": {
                "vacancies": [
                    {
                        "title": "t",
                        "category": category,
                        "shortDescription": "d",
                        "urlSlug": "u1",
                        "seoSlug": "grp/slug",
                        "cities": [],
                        "tags": [],
                    }
                ]
            }
        }
    )
    url = parse_tbank(payload)[0].url
    assert url == f"https://www.tbank.ru/career/{expected_segment}/vacancy/grp/slug/u1/"


def test_location_falls_back_to_city_when_subtitle_empty() -> None:
    """Пустой subtitle → город из cities."""
    vacancies = parse_tbank(load_payload("tbank", "vacancies.json"))
    remote = next(v for v in vacancies if v.title == "Head of Engineering")
    assert remote.location == "Удалённо"
