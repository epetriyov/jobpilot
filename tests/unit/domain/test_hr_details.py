"""T6G-1: схема HrDetails (correspondence) — выход LLM `hr_extract`.

`HrDetails(date: date|None, url: str|None, gist: str<=200)` — что извлекаем из
пересланного HR-сообщения (data-model §5). Дата/ссылка опциональны (в сообщении
может не быть), суть (gist) ограничена 200 знаками. Статус заявки схема не трогает —
это value object результата извлечения (C3).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.correspondence import HrDetails


def test_full_details_parsed() -> None:
    d = HrDetails(date=date(2026, 8, 20), url="https://meet.example/x", gist="Zoom в 15:00")
    assert d.date == date(2026, 8, 20)
    assert d.url == "https://meet.example/x"
    assert d.gist == "Zoom в 15:00"


def test_date_parsed_from_iso_string() -> None:
    d = HrDetails.model_validate({"date": "2026-08-20", "url": None, "gist": ""})
    assert d.date == date(2026, 8, 20)


def test_all_optional_empty() -> None:
    d = HrDetails()
    assert d.date is None
    assert d.url is None
    assert d.gist == ""


def test_gist_over_limit_rejected() -> None:
    with pytest.raises(ValidationError):
        HrDetails(gist="я" * 201)


def test_schema_is_frozen() -> None:
    d = HrDetails(gist="ok")
    with pytest.raises(ValidationError):
        d.gist = "изменили"  # type: ignore[misc]
