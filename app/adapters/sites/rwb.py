"""Адаптер карьерного портала RWB / Wildberries (career.rwb.ru) — лёгкая волна.

Источник: публичный CRM-gateway кандидатов
`GET /crm-api/api/v1/pub/vacancies?limit=50&offset=0` — cookieless, без авторизации
и анти-бота → `{"status": ..., "data": {"items": [...], "range": {...}}}`. Чистый
`parse_rwb(payload)` разбирает записанный JSON без I/O (golden, [S-C7]/[S-C8]);
транспорт (`HttpTransport`) даёт сырой payload — смена способа добычи не ломает
парсер (plan.md: транспорт↔парсер). Домен НЕ меняется.

Маппинг карточки → `Vacancy` (data-model.md §маппинг):
- `external_id` = `id` (стабильный числовой ключ вакансии, приводим к str);
- `title`     = `name`;
- `company`   = имя портала «rwb» (портал = один работодатель, единый ЮЛ);
- `url`       = `https://career.rwb.ru/vacancies/{id}` — абсолютный, без трекинга;
- `salary`    = отсутствует в публичном списке → пустая вилка;
- `location`  = `city_title`;
- `description_raw` = дедуп-склейка `direction_title` / `direction_role_title` /
              `experience_type_title` / `employment_types[].title` (пустые — мимо).
"""

from __future__ import annotations

import json
from typing import Any

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

SITE_NAME = "rwb"
# Портал = один работодатель (RWB / Wildberries): company карточки нет, берём портал.
COMPANY = "rwb"

# Публичный CRM-gateway кандидатов: отдаёт JSON без авторизации и анти-бота.
API_URL = "https://career.rwb.ru/crm-api/api/v1/pub/vacancies?limit=50&offset=0"

# Карточка вакансии маршрутизируется по числовому id.
_CARD_BASE = "https://career.rwb.ru/vacancies"


def _card_url(vacancy_id: int | str) -> str:
    return f"{_CARD_BASE}/{vacancy_id}"


def _location(item: dict[str, Any]) -> str | None:
    value = item.get("city_title")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _description(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("direction_title", "direction_role_title", "experience_type_title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    employment_types = item.get("employment_types")
    if isinstance(employment_types, list):
        for entry in employment_types:
            if isinstance(entry, dict):
                title = entry.get("title")
                if isinstance(title, str) and title.strip():
                    parts.append(title.strip())
    deduped: list[str] = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    return "\n".join(deduped)


def parse_rwb(payload: str) -> list[Vacancy]:
    """JSON списка вакансий → список `Vacancy` (дедуп по external_id).

    Деградация без исключения (S4): битый/пустой/анти-бот-payload → [].
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    container = data.get("data")
    items = container.get("items") if isinstance(container, dict) else None
    if not isinstance(items, list):
        return []

    vacancies: list[Vacancy] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        vacancy_id = item.get("id")
        title = item.get("name")
        if vacancy_id is None or not isinstance(title, str) or not title.strip():
            continue
        external_id = str(vacancy_id)
        if external_id in seen:
            continue
        seen.add(external_id)
        vacancies.append(
            Vacancy.create(
                source_ref=SourceRef(
                    source=Source.SITE, site_name=SITE_NAME, external_id=external_id
                ),
                title=title.strip(),
                company=COMPANY,
                url=_card_url(external_id),
                description_raw=_description(item),
                location=_location(item),
                extra_raw={"item": item},
            )
        )
    return vacancies


def rwb_factory(settings: Settings, escalate: EscalateFn | None = None) -> SiteAdapter:
    """Собирает `SiteAdapter` RWB: HttpTransport(JSON) → parse_rwb → EM-фильтр."""
    transport = HttpTransport(
        url=API_URL,
        method="GET",
        user_agent=settings.sites_user_agent,
        rate_limit_sec=settings.sites_rate_limit_sec,
        timeout_sec=settings.sites_timeout_sec,
        robots_respect=settings.sites_robots_respect,
    )
    return SiteAdapter(
        site_name=SITE_NAME,
        transport=transport,
        parse_fn=parse_rwb,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
