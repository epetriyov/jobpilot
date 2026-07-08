"""Правила отбора и few-shot (DOMAIN.md §3.2: R3, R4)."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.relevance.label import LabeledVacancy
from app.domain.relevance.score import Score

# якоря few-shot: «как выглядит хороший/плохой ответ» для размеченных примеров
RELEVANT_ANCHOR = 85
IRRELEVANT_ANCHOR = 15


def select_for_digest(
    scored: Sequence[tuple[str, Score]], *, threshold: int, max_items: int
) -> list[tuple[str, Score]]:
    """R4: в дайджест — score ≥ threshold, по убыванию, максимум max_items."""
    passed = [(ref, s) for ref, s in scored if s.value >= threshold]
    passed.sort(key=lambda pair: pair[1].value, reverse=True)
    return passed[:max_items]


def build_few_shot(
    labels: Sequence[LabeledVacancy], *, limit: int = 10, text_limit: int = 800
) -> list[tuple[str, str]]:
    """R3: до `limit` последних размеченных → пары (user, assistant) для промпта."""
    examples: list[tuple[str, str]] = []
    for label in list(labels)[:limit]:
        anchor = RELEVANT_ANCHOR if label.verdict == "relevant" else IRRELEVANT_ANCHOR
        verdict_ru = "релевантна" if label.verdict == "relevant" else "нерелевантна"
        text = label.description_text[:text_limit]
        user = f"{label.title} — {label.company}\n{text}"
        assistant = f'{{"score": {anchor}, "reason": "Пользователь отметил: {verdict_ru}"}}'
        examples.append((user, assistant))
    return examples
