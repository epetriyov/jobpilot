"""Стаб GetMatch-источника: механика этапа 4 без сети (fake-режим, CI, canary).

Реализует тот же `VacancySourcePort`, что и `GetMatchSource` — переключение на
реальный httpx = `GETMATCH_MODE=real` в конфиге, код не меняется. Детерминированный
обезличенный JSON прогоняется через продовый `parse_getmatch_offers`, поэтому стаб
проверяет тот же путь маппинга, что и боевой источник. Сеть/`getmatch.ru` не
трогаются (источник off-by-default, robots `Disallow: /api/`).
"""

from __future__ import annotations

import json

from app.adapters.getmatch.parser import parse_getmatch_offers
from app.domain.sourcing import Vacancy

# Обезличенный мини-фид `/api/offers`: открытая вилка, salary_hidden, инкогнито,
# закрытая (is_active=false, пропускается). Значения синтетические.
_STUB_OFFERS: list[dict[str, object]] = [
    {
        "id": 8001,
        "position": "Engineering Manager (Platform)",
        "company": {"name": "Ромашка Технологии"},
        "url": "/vacancies/8001-em-platform",
        "salary_display_from": 350000,
        "salary_display_to": 480000,
        "salary_currency": "RUB",
        "salary_hidden": False,
        "offer_description": "<p>EM в платформенную команду (12 инженеров), найм, 1:1.</p>",
        "skills_objects": [{"name": "Python"}, {"name": "Kubernetes"}],
        "location_items": [{"label": "Москва"}],
        "is_active": True,
    },
    {
        "id": 8002,
        "position": "Head of Engineering",
        "company": {"name": "Финтех Плюс"},
        "url": "/vacancies/8002-head-of-engineering",
        "salary_hidden": True,
        "offer_description": "<p>Руководство разработкой (3 команды, 25 человек), стратегия.</p>",
        "skills_objects": [{"name": "Go"}],
        "location_items": [{"label": "Санкт-Петербург"}],
        "is_active": True,
    },
    {
        "id": 8003,
        "position": "Team Lead (Backend)",
        "company": {"name": None},
        "url": "/vacancies/8003-team-lead-backend",
        "salary_display_from": 300000,
        "salary_display_to": None,
        "salary_currency": "RUB",
        "salary_hidden": False,
        "offer_description": "<p>Тимлид backend-команды (6 инженеров), инкогнито.</p>",
        "skills_objects": [{"name": "Java"}],
        "location_items": [{"label": "Удалённо"}],
        "is_active": True,
    },
    {
        "id": 8004,
        "position": "Руководитель группы разработки (закрытая)",
        "company": {"name": "Маркетплейс Юг"},
        "url": "/vacancies/8004-rukovoditel",
        "salary_hidden": True,
        "offer_description": "<p>Закрыта — не должна попасть в дайджест.</p>",
        "is_active": False,
    },
]


class FakeGetMatchSource:
    """`VacancySourcePort`: детерминированный обезличенный фид через прод-парсер."""

    name = "getmatch"

    async def fetch(self) -> list[Vacancy]:
        payload = json.dumps(
            {"meta": {"total": len(_STUB_OFFERS), "offset": 0, "limit": 20}, "offers": _STUB_OFFERS}
        )
        return parse_getmatch_offers(payload)
