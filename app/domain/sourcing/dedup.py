"""Дедупликация вакансий: инварианты S1 (по SourceRef) и S2 (кросс-источниковая)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.shared import SourceRef
from app.domain.sourcing.events import VacancyDiscovered
from app.domain.sourcing.vacancy import Vacancy

CROSS_SOURCE_WINDOW_DAYS = 30


class DedupIndex:
    """Чистая доменная модель реестра виденных вакансий.

    Хранение (seen_vacancy) — забота адаптера persistence; здесь — правила.
    """

    def __init__(self) -> None:
        self._first_seen: dict[str, datetime] = {}
        self._by_normalized: dict[str, tuple[SourceRef, datetime]] = {}

    def first_seen_at(self, ref: SourceRef) -> datetime | None:
        return self._first_seen.get(ref.as_key())

    def ingest(self, vacancy: Vacancy, *, now: datetime) -> VacancyDiscovered | None:
        """Обнаружение вакансии.

        S1: повторный SourceRef — не дубликат записи, first_seen_at неизменен.
        S2: та же нормализованная (company, title) из другого источника за 30 дней —
            пометка duplicate_of, в дайджест не идёт.
        """
        key = vacancy.source_ref.as_key()
        if key in self._first_seen:
            return None

        self._first_seen[key] = now

        norm_key = vacancy.normalized_key()
        known = self._by_normalized.get(norm_key)
        if known is not None:
            original_ref, seen_at = known
            if now - seen_at <= timedelta(days=CROSS_SOURCE_WINDOW_DAYS):
                vacancy.mark_duplicate_of(original_ref)
                return None

        self._by_normalized[norm_key] = (vacancy.source_ref, now)
        return VacancyDiscovered(source_ref=vacancy.source_ref, occurred_at=now)
