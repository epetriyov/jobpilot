"""Label — ручной вердикт владельца со снапшотом вакансии (DOMAIN.md §1, §3.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.shared import SourceRef

Verdict = Literal["relevant", "irrelevant"]


class VacancySnapshot(BaseModel):
    """Снапшот вакансии из реестра виденных (seen_vacancy, поля этапа 1).

    Достаточен для скоринга и разметки без повторного похода в источник —
    вакансия может быть уже удалена с HH (edge case спеки этапа 1).
    """

    model_config = ConfigDict(frozen=True)

    source_ref: SourceRef
    title: str
    company: str
    url: str
    description_text: str


class LabeledVacancy(VacancySnapshot):
    """Снапшот размеченной вакансии — топливо few-shot и eval (DOMAIN.md §4)."""

    verdict: Verdict
