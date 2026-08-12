"""Адаптер карьерного портала Сбер (rabota.sber.ru) — лёгкая волна (публичный JSON).

Источник: публичный gateway кандидатов
`GET /public/app-candidate-public-api-gateway/api/v1/publications?skip=0&take=50`
→ `{"data": {"vacancies": [...]}}`. Чистый `parse_sber(payload)` разбирает записанный
JSON без I/O (golden, [S-C7]/[S-C8]); транспорт (`HttpTransport`) даёт сырой payload —
смена способа добычи не ломает парсер (plan.md: транспорт↔парсер). Домен НЕ меняется.

Маппинг карточки → `Vacancy` (data-model.md §маппинг):
- `external_id` = `publicationId` (стабильный uuid публикации; fallback → `internalId`);
- `title`     = `title`;
- `company`   = имя портала «sber» (портал = один работодатель), НЕ поле `company` карточки;
- `url`       = `https://rabota.sber.ru/search/{internalId}/` — абсолютный, без трекинга;
              портал 307-редиректит на канонический slug-URL, но числовой internalId —
              стабильный детерминированный ключ маршрута (проверено 2026-08-12);
- `salary`    = `salary_min`/`salary_max` (RUR, могут быть null);
- `location`  = `city`/`region` (склейка непустых);
- `description_raw` = склейка `duties` + `requirements` + `conditions`.
"""

from __future__ import annotations

import json
from typing import Any

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy

SITE_NAME = "sber"

# Публичный gateway кандидатов (XHR-спайк 2026-08-12): отдаёт JSON без авторизации.
PUBLICATIONS_URL = (
    "https://rabota.sber.ru/public/app-candidate-public-api-gateway"
    "/api/v1/publications?skip=0&take=50"
)

# Карточка вакансии маршрутизируется по числовому internalId; портал редиректит на
# канонический slug-URL. Числовой ключ детерминирован и не требует транслитерации.
_CARD_BASE = "https://rabota.sber.ru/search"


def _card_url(internal_id: int | str) -> str:
    return f"{_CARD_BASE}/{internal_id}/"


def _salary(card: dict[str, Any]) -> Salary:
    salary_from = card.get("salary_min")
    salary_to = card.get("salary_max")
    if salary_from is None and salary_to is None:
        return Salary()
    return Salary(from_=salary_from, to=salary_to, currency="RUR")


def _location(card: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("city", "region"):
        value = card.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return ", ".join(parts) or None


def _description(card: dict[str, Any]) -> str:
    blocks = [card.get(key) for key in ("duties", "requirements", "conditions")]
    return "\n\n".join(b.strip() for b in blocks if isinstance(b, str) and b.strip())


def parse_sber(payload: str) -> list[Vacancy]:
    """JSON списка публикаций → список `Vacancy` (дедуп по external_id).

    Деградация без исключения (S4): битый/пустой/анти-бот-payload → [].
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    container = data.get("data")
    cards = container.get("vacancies") if isinstance(container, dict) else None
    if not isinstance(cards, list):
        return []

    vacancies: list[Vacancy] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        internal_id = card.get("internalId")
        title = card.get("title")
        if internal_id is None or not isinstance(title, str) or not title.strip():
            continue
        publication_id = card.get("publicationId")
        external_id = str(publication_id) if publication_id else str(internal_id)
        if external_id in seen:
            continue
        seen.add(external_id)
        vacancies.append(
            Vacancy.create(
                source_ref=SourceRef(
                    source=Source.SITE, site_name=SITE_NAME, external_id=external_id
                ),
                title=title.strip(),
                company=SITE_NAME,
                url=_card_url(internal_id),
                description_raw=_description(card),
                salary=_salary(card),
                location=_location(card),
                extra_raw={"card": card},
            )
        )
    return vacancies


def sber_factory(settings: Settings, escalate: EscalateFn | None = None) -> SiteAdapter:
    """Собирает `SiteAdapter` Сбера: HttpTransport(JSON) → parse_sber → EM-фильтр."""
    transport = HttpTransport(
        url=PUBLICATIONS_URL,
        method="GET",
        user_agent=settings.sites_user_agent,
        rate_limit_sec=settings.sites_rate_limit_sec,
        timeout_sec=settings.sites_timeout_sec,
        robots_respect=settings.sites_robots_respect,
    )
    return SiteAdapter(
        site_name=SITE_NAME,
        transport=transport,
        parse_fn=parse_sber,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
