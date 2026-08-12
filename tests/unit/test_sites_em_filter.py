"""[T504][S-C7] filter_em (FR-004): адаптерный EM/лид-фильтр до скоринга.

Чистая функция над списком Vacancy: оставляет только руководящие/EM-роли по
ключам конфига — чтобы не гнать сотни нерелевантных карточек в LLM-скоринг.
"""

from __future__ import annotations

from app.adapters.sites.em_filter import filter_em
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

KEYWORDS = ["engineering manager", "руководитель разработки", "head of engineering", "тимлид"]


def _vac(title: str) -> Vacancy:
    return Vacancy.create(
        source_ref=SourceRef(source=Source.SITE, site_name="yandex", external_id=title),
        title=title,
        company="Яндекс",
        url="https://yandex.ru/jobs/vacancies/1",
        description_raw="",
    )


def test_keeps_only_em_and_lead_roles() -> None:
    vacancies = [
        _vac("Engineering Manager"),
        _vac("Senior Python Developer"),
        _vac("Руководитель разработки бэкенда"),
        _vac("QA Engineer"),
        _vac("Тимлид команды платформы"),
    ]
    kept = filter_em(vacancies, KEYWORDS)
    assert [v.title for v in kept] == [
        "Engineering Manager",
        "Руководитель разработки бэкенда",
        "Тимлид команды платформы",
    ]


def test_case_insensitive() -> None:
    assert filter_em([_vac("ENGINEERING manager")], KEYWORDS)
    assert filter_em([_vac("head of ENGINEERING")], KEYWORDS)


def test_empty_keywords_keeps_all() -> None:
    """Пустой список ключей → фильтр не сужает (owner ещё не задал ключи)."""
    vacancies = [_vac("Anything"), _vac("Another")]
    assert filter_em(vacancies, []) == vacancies


def test_no_match_yields_empty() -> None:
    assert filter_em([_vac("Data Scientist"), _vac("SRE")], KEYWORDS) == []


def test_pure_does_not_mutate_input() -> None:
    vacancies = [_vac("Engineering Manager"), _vac("Developer")]
    before = list(vacancies)
    filter_em(vacancies, KEYWORDS)
    assert vacancies == before
