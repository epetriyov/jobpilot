"""Golden + деградация чистого парсера GetMatch ([S-C5]/[S-C6]/[S-C0b]-аналог).

Транспорт↔парсер (plan.md): `parse_getmatch_offers` тестируется на записанном
обезличенном JSON-ответе `/api/offers`, независимо от способа добычи. Golden ловит
слом структуры; отдельные кейсы — маппинг вилки/HTML, пропуск закрытых/непарсенных,
дедуп внутри батча (S1), чтение `meta` для пагинации.
"""

from __future__ import annotations

import json

from app.adapters.getmatch.parser import parse_getmatch_offers, read_meta
from app.domain.shared import Source
from tests.golden.getmatch.harness import assert_golden, load_expected, load_payload


def test_parse_getmatch_golden() -> None:
    payload = load_payload("offers.json")
    expected = load_expected("offers.expected.json")
    assert_golden(parse_getmatch_offers(payload), expected)


def test_source_getmatch_enum_value() -> None:
    # T403: значение единого языка DOMAIN §1 присутствует (домен не меняется).
    assert Source.GETMATCH == "getmatch"
    first = parse_getmatch_offers(load_payload("offers.json"))[0]
    assert first.source_ref.source is Source.GETMATCH
    assert first.source_ref.site_name is None


def test_salary_hidden_yields_empty_salary() -> None:
    by_id = {
        v.source_ref.external_id: v for v in parse_getmatch_offers(load_payload("offers.json"))
    }
    hidden = by_id["40002"]
    assert hidden.salary.from_ is None
    assert hidden.salary.to is None
    assert hidden.salary.currency is None


def test_open_range_and_partial_range() -> None:
    by_id = {
        v.source_ref.external_id: v for v in parse_getmatch_offers(load_payload("offers.json"))
    }
    assert (by_id["40001"].salary.from_, by_id["40001"].salary.to) == (350000, 480000)
    # только from без to (S1: поля Salary опциональны)
    assert (by_id["40003"].salary.from_, by_id["40003"].salary.to) == (300000, None)


def test_incognito_company_uses_placeholder() -> None:
    by_id = {
        v.source_ref.external_id: v for v in parse_getmatch_offers(load_payload("offers.json"))
    }
    assert by_id["40003"].company == "GetMatch (скрыто)"


def test_inactive_offer_skipped() -> None:
    ids = {v.source_ref.external_id for v in parse_getmatch_offers(load_payload("offers.json"))}
    assert "40004" not in ids  # is_active=false → пропущен


def test_url_absolutized() -> None:
    first = parse_getmatch_offers(load_payload("offers.json"))[0]
    assert first.url == "https://getmatch.ru/vacancies/40001-engineering-manager-platform"


def test_description_text_cleaned_and_enriched() -> None:
    by_id = {
        v.source_ref.external_id: v for v in parse_getmatch_offers(load_payload("offers.json"))
    }
    text = by_id["40001"].description_text
    assert "<b>" not in text and "<p>" not in text  # S3: HTML очищен
    assert "Python" in text and "Kubernetes" in text  # стек из skills_objects — скорингу
    assert "Москва" in text  # локация — скорингу
    # оригинальный HTML сохранён в raw (S3)
    assert "<b>" in by_id["40001"].raw["description"]


def test_raw_keeps_original_offer() -> None:
    first = parse_getmatch_offers(load_payload("offers.json"))[0]
    assert first.raw["offer"]["id"] == 40001
    assert first.raw["offer"]["salary_taxes"] == "net"


def test_dedup_by_id_within_batch() -> None:
    payload = load_payload("offers.json")
    data = json.loads(payload)
    doubled = json.dumps({"meta": data["meta"], "offers": data["offers"] + data["offers"]})
    vacancies = parse_getmatch_offers(doubled)
    ids = [v.source_ref.external_id for v in vacancies]
    assert len(ids) == len(set(ids))  # повтор id в выдаче не даёт второй DTO


def test_unknown_format_yields_nothing() -> None:
    # [S-C6]: offers без position/url или «чужой» схемы → VacancyDTO не создаётся.
    assert parse_getmatch_offers(load_payload("offers_unknown_format.json")) == []


def test_broken_and_empty_payload_degrade_to_empty() -> None:
    assert parse_getmatch_offers("") == []
    assert parse_getmatch_offers("<html>anti-bot wall</html>") == []
    assert parse_getmatch_offers(json.dumps({"meta": {}, "offers": []})) == []
    assert parse_getmatch_offers(json.dumps({"unexpected": True})) == []


def test_read_meta_total_and_offer_count() -> None:
    meta = read_meta(load_payload("offers.json"))
    assert meta.total == 6
    assert meta.offer_count == 6


def test_read_meta_on_garbage() -> None:
    meta = read_meta("<html/>")
    assert meta.total is None
    assert meta.offer_count == 0
