"""Чистая логика одобрения сайтов-скрейперов (`/approve_scraper`, этап 5).

Отделено от Services (нет I/O) — тестируется без БД. Валидация имени сайта и
список доступных для одобрения (constitution VI, FR-007).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from app.config import KNOWN_SITES

ApprovalOutcome = Literal["approved", "already", "unknown"]


def is_known_site(site: str) -> bool:
    return site in KNOWN_SITES


def available_scrapers(*, canary: Sequence[str], active: Sequence[str]) -> list[str]:
    """Сайты, которые владелец может одобрить: настроенные canary+active.

    Пусто в конфиге → показываем всё множество известных сайтов как подсказку.
    """
    configured = sorted(set(canary) | set(active))
    return configured or sorted(KNOWN_SITES)
