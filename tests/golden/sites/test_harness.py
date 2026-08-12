"""[T505][S-C8] Самопроверка golden-харнесса на демонстрационном парсере.

Доказывает механизм, который переиспользуют по-сайтовые парсеры parse_<site>:
корректный парсер сходится с эталоном; «поплывшая» структура → падение с diff.
Демо-парсер живёт в тесте — реальные parse_<site> добавят по-сайтовые задачи.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy
from tests.golden.sites.harness import assert_golden, dto_shape, load_expected, load_payload


def sample_parse(payload: str) -> list[Vacancy]:
    """Демо-парсер: JSON {vacancies:[...]} → список Vacancy (маппинг data-model)."""
    data: dict[str, Any] = json.loads(payload)
    result: list[Vacancy] = []
    for card in data["vacancies"]:
        result.append(
            Vacancy.create(
                source_ref=SourceRef(
                    source=Source.SITE, site_name="sample", external_id=card["id"]
                ),
                title=card["title"],
                company="Sample Corp",
                url=f"https://sample.example/jobs/{card['slug']}",
                description_raw="",
                salary=Salary(
                    from_=card["salary_from"],
                    to=card["salary_to"],
                    currency=card["currency"],
                ),
                location=card["city"],
            )
        )
    return result


def test_golden_matches_recorded_payload() -> None:
    vacancies = sample_parse(load_payload("sample", "payload.json"))
    assert_golden(vacancies, load_expected("sample", "expected.json"))


def test_dto_shape_is_stable_projection() -> None:
    vacancies = sample_parse(load_payload("sample", "payload.json"))
    shape = dto_shape(vacancies[0])
    assert shape["external_id"] == "em-001"
    assert shape["company"] == "Sample Corp"  # портал = один работодатель
    assert shape["salary_from"] == 350000


def test_broken_structure_fails_with_diff() -> None:
    """[S-C8]: изменённый эталон → харнесс падает (сигнал «скрейпер сломан»)."""
    vacancies = sample_parse(load_payload("sample", "payload.json"))
    tampered = load_expected("sample", "expected.json")
    tampered[0]["title"] = "СЛОМАНО"
    with pytest.raises(AssertionError):
        assert_golden(vacancies, tampered)
