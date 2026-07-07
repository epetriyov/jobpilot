"""Демо-фикстуры источников для DRY_RUN-смоука этапа 0 (реальные источники — этап 1+)."""

from __future__ import annotations

from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy


def _v(external_id: str, title: str, company: str, desc: str) -> Vacancy:
    return Vacancy.create(
        source_ref=SourceRef(source=Source.HH, external_id=external_id),
        title=title,
        company=company,
        url=f"https://hh.ru/vacancy/{external_id}",
        description_raw=desc,
    )


def sample_hh() -> list[Vacancy]:
    return [
        _v("101", "Engineering Manager", "Acme", "<p>Руководство командой из 8 инженеров</p>"),
        _v("102", "Head of Engineering", "Globex", "<p>Строим платформу с нуля</p>"),
    ]


def sample_sources() -> dict[str, object]:
    return {"hh": sample_hh}
