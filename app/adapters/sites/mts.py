"""Адаптер карьерного портала МТС (job.mts.ru) — лёгкая волна (публичный JSON).

Источник (XHR-спайк 2026-08-13, честный UA `JobPilot/1.0 (+owner-contact)`):
портал — Nuxt-SPA, список вакансий грузится клиентом из публичного каталога
`GET https://job.mts.ru/api/v2/catalog/v1/vacancies?limit=50&offset=0`
→ `{"data": [...], "meta": {"pagination": {...}}}`. Эндпоинт отдаёт JSON без
авторизации (публичный apiKey из runtime-config не требуется для чтения каталога).
robots.txt (`User-agent: *`): `/api/...` и `/jobs/...` НЕ запрещены (проверено
protego); disallow висит на трекинг-параметрах (`*from=*`, `*ref=*`, `*search=*`…),
которых в `limit`/`offset`-запросе нет. Чистый `parse_mts(payload)` разбирает
записанный JSON без I/O (golden, [S-C7]/[S-C8]); транспорт (`HttpTransport`) даёт
сырой payload — смена способа добычи не ломает парсер (plan.md: транспорт↔парсер).

Маппинг карточки → `Vacancy` (data-model.md §маппинг):
- `external_id` = `id` (стабильный opaque-идентификатор публикации);
- `title`     = `title`;
- `company`   = имя портала «mts» (портал = единый работодатель группы МТС), НЕ
              поле `employer.title` карточки — оно кладётся в `raw` для контекста;
- `url`       = `externalUrl` (канонический `https://job.mts.ru/jobs/{num}`),
              очищенный от трекинга;
- `salary`    = `salary.from`/`salary.to`/`salary.currency` (RUB, может быть null);
- `location`  = склейка `cities[].title`;
- `description_raw` = `summary` (в списке часто пуст → "").
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy

SITE_NAME = "mts"
COMPANY = "mts"  # портал = единый работодатель группы (data-model.md §маппинг)

# Публичный каталог кандидатов (Nuxt apiBase `/api/v2` + клиент `/catalog/v1`).
# limit=50 — одна вежливая страница списка; пагинация (offset) — вне лёгкой волны.
LIST_URL = "https://job.mts.ru/api/v2/catalog/v1/vacancies?limit=50&offset=0"

# Трекинг-параметры, вычищаемые из url карточки (robots Clean-Param + типовой набор).
_TRACKING_PREFIXES = ("utm_", "yclid", "_openstat", "gclid", "clid", "from", "ref", "erid")


def _clean_url(url: str) -> str:
    """Абсолютный url карточки без tracking-хвоста (data-model.md §маппинг)."""
    parts = urlsplit(url)
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _salary(card: dict[str, Any]) -> Salary:
    salary = card.get("salary")
    if not isinstance(salary, dict):
        return Salary()
    salary_from = salary.get("from")
    salary_to = salary.get("to")
    if salary_from is None and salary_to is None:
        return Salary()
    currency = salary.get("currency")
    return Salary(
        from_=salary_from,
        to=salary_to,
        currency=currency if isinstance(currency, str) and currency.strip() else None,
    )


def _location(card: dict[str, Any]) -> str | None:
    cities = card.get("cities")
    if not isinstance(cities, list):
        return None
    parts: list[str] = []
    for city in cities:
        if isinstance(city, dict):
            name = city.get("title")
            if isinstance(name, str) and name.strip() and name.strip() not in parts:
                parts.append(name.strip())
    return ", ".join(parts) or None


def _description(card: dict[str, Any]) -> str:
    summary = card.get("summary")
    return summary.strip() if isinstance(summary, str) else ""


def _card_url(card: dict[str, Any]) -> str | None:
    external_url = card.get("externalUrl")
    if isinstance(external_url, str) and external_url.strip():
        return _clean_url(external_url.strip())
    return None


def parse_mts(payload: str) -> list[Vacancy]:
    """JSON каталога вакансий → список `Vacancy` (дедуп по external_id).

    Деградация без исключения (S4): битый/пустой/анти-бот-payload → []. Карточки
    без id/title/url пропускаются (нет стабильного ключа/обязательного поля).
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    cards = data.get("data")
    if not isinstance(cards, list):
        return []

    vacancies: list[Vacancy] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        raw_id = card.get("id")
        title = card.get("title")
        if raw_id is None or not isinstance(title, str) or not title.strip():
            continue
        url = _card_url(card)
        if url is None:
            continue
        external_id = str(raw_id)
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
                url=url,
                description_raw=_description(card),
                salary=_salary(card),
                location=_location(card),
                extra_raw={"card": card},
            )
        )
    return vacancies


def mts_factory(settings: Settings, escalate: EscalateFn | None = None) -> SiteAdapter:
    """Собирает `SiteAdapter` МТС: HttpTransport(JSON, GET) → parse_mts → EM-фильтр."""
    transport = HttpTransport(
        url=LIST_URL,
        method="GET",
        user_agent=settings.sites_user_agent,
        rate_limit_sec=settings.sites_rate_limit_sec,
        timeout_sec=settings.sites_timeout_sec,
        robots_respect=settings.sites_robots_respect,
    )
    return SiteAdapter(
        site_name=SITE_NAME,
        transport=transport,
        parse_fn=parse_mts,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
