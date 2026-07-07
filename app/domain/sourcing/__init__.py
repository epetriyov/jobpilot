"""Контекст SOURCING: вакансии и дедуп (DOMAIN.md §3.1)."""

from app.domain.sourcing.collect import CollectResult, SourceFetcher, collect_from_sources
from app.domain.sourcing.dedup import CROSS_SOURCE_WINDOW_DAYS, DedupIndex
from app.domain.sourcing.events import SourceFetchFailed, VacancyDiscovered
from app.domain.sourcing.vacancy import (
    Vacancy,
    clean_html,
    content_hash,
    normalize_company_title,
)

__all__ = [
    "CROSS_SOURCE_WINDOW_DAYS",
    "CollectResult",
    "DedupIndex",
    "SourceFetchFailed",
    "SourceFetcher",
    "Vacancy",
    "VacancyDiscovered",
    "clean_html",
    "collect_from_sources",
    "content_hash",
    "normalize_company_title",
]
