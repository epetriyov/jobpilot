"""[T510] Golden + краевые случаи чистого парсера Яндекс-портала (SSR-HTML).

parse_yandex — чистая функция над HTML списка вакансий yandex.ru/jobs/vacancies
(вакансии в исходном HTML, внутреннего JSON-эндпоинта нет — зонд 2026-08-12).
Golden ловит слом SSR-вёрстки ([S-C7]/[S-C8]); отдельные тесты фиксируют инварианты
маппинга (data-model.md §маппинг): company='yandex', url без tracking, external_id из
url (числовой id → он; иначе slug), salary не публикуется, дедуп по external_id.
"""

from __future__ import annotations

from app.adapters.sites.yandex import parse_yandex
from tests.golden.sites.harness import assert_golden, load_expected, load_payload


def test_golden_matches_recorded_payload() -> None:
    vacancies = parse_yandex(load_payload("yandex", "list.html"))
    assert_golden(vacancies, load_expected("yandex", "list.expected.json"))


def test_company_is_portal_owner() -> None:
    vacancies = parse_yandex(load_payload("yandex", "list.html"))
    assert vacancies, "фикстура должна содержать вакансии"
    assert {v.company for v in vacancies} == {"yandex"}


def test_source_ref_is_site_yandex() -> None:
    v = parse_yandex(load_payload("yandex", "list.html"))[0]
    assert v.source_ref.source == "site"
    assert v.source_ref.site_name == "yandex"


def test_numeric_external_id_from_url_tail() -> None:
    by_id = {v.source_ref.external_id: v for v in parse_yandex(load_payload("yandex", "list.html"))}
    assert "47824" in by_id  # slug ...-47824 → числовой id
    assert by_id["47824"].url.endswith("/sre-v-poisk-47824")


def test_slug_fallback_when_no_numeric_id() -> None:
    by_id = {v.source_ref.external_id: v for v in parse_yandex(load_payload("yandex", "list.html"))}
    # карточка без числового хвоста в slug → external_id = сам slug (не хеш)
    assert "trener_himiya" in by_id


def test_url_has_no_tracking() -> None:
    for v in parse_yandex(load_payload("yandex", "list.html")):
        low = v.url.lower()
        assert "utm_" not in low
        assert "yclid" not in low
        assert "?" not in v.url  # у карточек списка трекинг-хвостов нет — не протекают


def test_dedup_by_external_id() -> None:
    payload = load_payload("yandex", "list.html")
    doubled = payload + payload  # тот же список дважды → те же external_id
    vacancies = parse_yandex(doubled)
    ids = [v.source_ref.external_id for v in vacancies]
    assert len(ids) == len(set(ids))


def test_salary_is_absent() -> None:
    # Яндекс-список зарплату не публикует (зонд 2026-08-12) → пустая вилка, без мусора.
    for v in parse_yandex(load_payload("yandex", "list.html")):
        assert v.salary.from_ is None
        assert v.salary.to is None
        assert v.salary.currency is None


def test_empty_payload_returns_empty() -> None:
    assert parse_yandex("") == []


def test_garbage_payload_returns_empty() -> None:
    assert parse_yandex("<html><body><p>ничего похожего на вакансии</p></body></html>") == []


def test_broken_html_does_not_raise() -> None:
    # оборванная разметка (частичная загрузка) → парсер не падает, отдаёт что смог
    partial = load_payload("yandex", "list.html")[:1500]
    result = parse_yandex(partial)
    assert isinstance(result, list)
