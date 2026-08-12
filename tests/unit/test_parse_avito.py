"""[T5xx][S-C7] Golden парсера Avito career (SSR-HTML career.avito.com/vacancies/).

Записанный обезличённый фрагмент списка (4 карточки: пустая team, мультигород,
лид-роли) → parse_avito → сверка с эталоном формы. Слом SSR-вёрстки Avito ловится
diff-сигналом харнесса. Транспорт/добыча в golden не участвуют (parse — чистая).
"""

from __future__ import annotations

from app.adapters.sites.avito import parse_avito
from tests.golden.sites.harness import assert_golden, load_expected, load_payload


def test_golden_matches_recorded_payload() -> None:
    vacancies = parse_avito(load_payload("avito", "list.html"))
    assert_golden(vacancies, load_expected("avito", "list.expected.json"))


def test_company_is_avito_and_url_has_no_tracking() -> None:
    vacancies = parse_avito(load_payload("avito", "list.html"))
    assert vacancies, "фрагмент содержит карточки — парсер не должен вернуть пусто"
    for v in vacancies:
        assert v.company == "avito"  # портал = один работодатель
        assert v.source_ref.site_name == "avito"
        assert v.url.startswith("https://career.avito.com/vacancies/")
        assert "?" not in v.url and "utm" not in v.url


def test_external_id_is_url_card_id() -> None:
    vacancies = parse_avito(load_payload("avito", "list.html"))
    ids = [v.source_ref.external_id for v in vacancies]
    # id берётся из URL карточки (стабильный ключ), не из data-vacancy-id
    assert ids == ["19847", "20113", "19604", "19100"]


def test_description_carries_department_and_team() -> None:
    vacancies = parse_avito(load_payload("avito", "list.html"))
    by_id = {v.source_ref.external_id: v for v in vacancies}
    # секция + команда; пустая команда не порождает висящий разделитель
    assert by_id["19847"].description_text == "Аналитика данных"
    assert by_id["19604"].description_text == "Разработка · Услуги"


def test_dedup_by_external_id() -> None:
    payload = load_payload("avito", "list.html")
    # тот же фрагмент, склеенный дважды → дубли карточек схлопываются по external_id
    vacancies = parse_avito(payload + payload)
    ids = [v.source_ref.external_id for v in vacancies]
    assert ids == ["19847", "20113", "19604", "19100"]


def test_empty_payload_returns_empty_list() -> None:
    assert parse_avito("") == []
    assert parse_avito("<html><body>нет вакансий</body></html>") == []
