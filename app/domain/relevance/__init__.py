"""Контекст RELEVANCE: скоринг и разметка (DOMAIN.md §3.2)."""

from app.domain.relevance.label import LabeledVacancy, VacancySnapshot, Verdict
from app.domain.relevance.score import LlmScore, Score
from app.domain.relevance.selection import build_few_shot, select_for_digest

__all__ = [
    "LabeledVacancy",
    "LlmScore",
    "Score",
    "VacancySnapshot",
    "Verdict",
    "build_few_shot",
    "select_for_digest",
]
