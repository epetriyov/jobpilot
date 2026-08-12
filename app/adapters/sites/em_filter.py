"""Адаптерный EM/лид-фильтр (FR-004): чистая функция над списком Vacancy.

Отсекает нерелевантные роли ДО скоринга (экономия LLM-токенов). Фильтр —
адаптерный, домен и скоринг не трогаются (constitution I, plan.md).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.sourcing import Vacancy


def filter_em(vacancies: Sequence[Vacancy], keywords: Sequence[str]) -> list[Vacancy]:
    """Оставить вакансии, чей заголовок содержит хотя бы один EM/лид-ключ.

    Пустой список ключей → фильтр не сужает (owner ещё не задал ключи).
    Регистронезависимо; вход не мутируется.
    """
    if not keywords:
        return list(vacancies)
    needles = [k.casefold() for k in keywords if k.strip()]
    if not needles:
        return list(vacancies)
    return [v for v in vacancies if any(n in v.title.casefold() for n in needles)]
