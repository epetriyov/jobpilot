"""Golden-харнесс GetMatch ([S-C5]/[S-C0b]-аналог): payload → parse_getmatch_offers → эталон.

Зеркало `tests/golden/sites/harness.py`, но контрактная форма проверяет источник
`getmatch` (не `site`): изменение структуры ответа `/api/offers` → падение с
diff-сигналом «парсер GetMatch сломан». Харнесс не зависит от способа добычи
(транспорт↔парсер): чистый parser на записанном обезличенном JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.sourcing import Vacancy

GOLDEN_ROOT = Path(__file__).parent


def load_payload(name: str) -> str:
    """Записанный сырой JSON-ответ `/api/offers` (обезличенный)."""
    return (GOLDEN_ROOT / name).read_text(encoding="utf-8")


def load_expected(name: str) -> list[dict[str, Any]]:
    """Эталонные DTO-формы (список словарей контракта)."""
    return json.loads((GOLDEN_ROOT / name).read_text(encoding="utf-8"))


def dto_shape(vacancy: Vacancy) -> dict[str, Any]:
    """Контрактная форма карточки — стабильная проекция домена для golden-diff."""
    ref = vacancy.source_ref
    assert ref.source == "getmatch", f"источник GetMatch обязан быть getmatch, а не {ref.source}"
    assert ref.site_name is None, "site_name не применим к source=getmatch"
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
    assert shapes == expected, "golden-diff: парсер GetMatch сломан — структура ответа изменилась"
