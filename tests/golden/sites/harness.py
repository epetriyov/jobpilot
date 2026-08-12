"""Golden-харнесс сайтов ([S-C7]/[S-C8]): payload → parse_<site> → сверка с эталоном.

Переиспользуется по-сайтовыми задачами (T510+): каждый parse_<site> тестируется
на записанном payload; изменение структуры ответа → падение с diff-сигналом
«скрейпер <site> сломан». Харнесс не зависит от способа добычи (транспорт↔парсер).

Контракт формы (data-model.md §маппинг): external_id/title/company/url обязательны;
location опционален (≥90%); salary — from/to/currency опциональны.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.sourcing import Vacancy

GOLDEN_ROOT = Path(__file__).parent


def load_payload(site: str, name: str) -> str:
    """Записанный сырой ответ портала (HTML/JSON-строка)."""
    return (GOLDEN_ROOT / site / name).read_text(encoding="utf-8")


def load_expected(site: str, name: str) -> list[dict[str, Any]]:
    """Эталонные DTO-формы (список словарей контракта)."""
    return json.loads((GOLDEN_ROOT / site / name).read_text(encoding="utf-8"))


def dto_shape(vacancy: Vacancy) -> dict[str, Any]:
    """Контрактная форма карточки — стабильная проекция домена для golden-diff."""
    ref = vacancy.source_ref
    assert ref.source == "site", f"источник сайта обязан быть SITE, а не {ref.source}"
    assert ref.site_name, "site_name обязателен для source=site"
    return {
        "external_id": ref.external_id,
        "title": vacancy.title,
        "company": vacancy.company,
        "url": vacancy.url,
        "location": vacancy.location,
        "salary_from": vacancy.salary.from_,
        "salary_to": vacancy.salary.to,
        "salary_currency": vacancy.salary.currency,
    }


def assert_golden(actual: list[Vacancy], expected: list[dict[str, Any]]) -> None:
    """Сверка результата парсера с эталоном; расхождение → AssertionError с diff."""
    shapes = [dto_shape(v) for v in actual]
    assert shapes == expected, "golden-diff: скрейпер сломан — структура ответа изменилась"
