"""Чистый парсер публичного JSON GetMatch `GET /api/offers` (этап 4, [S-C5]).

`parse_getmatch_offers(payload)` — чистая функция без I/O над сырым JSON-ответом:
маппинг offer → `Vacancy` (data-model.md §маппинг), дедуп по `id` внутри батча (S1),
очистка HTML `offer_description` (S3), обработка `salary_hidden`/частичной вилки,
пропуск `is_active=false` и непарсенных offers ([S-C6]). Golden-diff ловит слом
структуры ответа ([S-C0b]-аналог).

Транспорт↔парсер (plan.md): добыча (пагинация/rate-limit/robots) живёт в
`source.py`; здесь — только разбор строки. Деградация без исключения: битый/пустой
payload → `[]` (S4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeGuard

from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy

_BASE_URL = "https://getmatch.ru"
# Инкогнито-публикация (`company.name=null`): домен требует `company: str`,
# поэтому вместо None — честный плейсхолдер (data-model.md §маппинг).
_INCOGNITO_COMPANY = "GetMatch (скрыто)"


@dataclass(frozen=True)
class OffersMeta:
    """Срез `meta` + число offers на странице — для пагинации в адаптере."""

    total: int | None
    offer_count: int


def read_meta(payload: str) -> OffersMeta:
    """`meta.total` и число offers на странице; на битом/непонятном payload — (None, 0)."""
    data = _loads(payload)
    if data is None:
        return OffersMeta(total=None, offer_count=0)
    meta = data.get("meta")
    total = meta.get("total") if isinstance(meta, dict) else None
    if not isinstance(total, int):
        total = None
    offers = data.get("offers")
    count = len(offers) if isinstance(offers, list) else 0
    return OffersMeta(total=total, offer_count=count)


def parse_getmatch_offers(payload: str) -> list[Vacancy]:
    """JSON-ответ `/api/offers` → список `Vacancy` (дедуп по `id`).

    Деградация без исключения (S4): битый/пустой/не-JSON payload → []. Offer без
    `position`/`url`, `is_active=false` или «чужой» схемы → пропускается ([S-C6]).
    """
    data = _loads(payload)
    if data is None:
        return []
    offers = data.get("offers")
    if not isinstance(offers, list):
        return []

    vacancies: list[Vacancy] = []
    seen: set[str] = set()
    for offer in offers:
        vacancy = _map_offer(offer)
        if vacancy is None:
            continue
        key = vacancy.source_ref.external_id
        if key in seen:
            continue
        seen.add(key)
        vacancies.append(vacancy)
    return vacancies


def _loads(payload: str) -> dict[str, Any] | None:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _map_offer(offer: Any) -> Vacancy | None:
    if not isinstance(offer, dict):
        return None
    if offer.get("is_active") is False:  # закрытые не показываем (data-model.md)
        return None
    external_id = offer.get("id")
    title = offer.get("position")
    url_path = offer.get("url")
    # position и url обязательны — иначе offer уходит в raw «непарсенное» ([S-C6]).
    if external_id is None or not _nonempty(title) or not _nonempty(url_path):
        return None

    description_raw = _enriched_description(offer)
    return Vacancy.create(
        source_ref=SourceRef(source=Source.GETMATCH, external_id=str(external_id)),
        title=title.strip(),
        company=_company(offer),
        url=_absolute_url(url_path.strip()),
        description_raw=description_raw,
        salary=_salary(offer),
        location=_location(offer),
        extra_raw={"offer": offer},
    )


def _nonempty(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _company(offer: dict[str, Any]) -> str:
    company = offer.get("company")
    name = company.get("name") if isinstance(company, dict) else None
    return name.strip() if _nonempty(name) else _INCOGNITO_COMPANY


def _absolute_url(url_path: str) -> str:
    if url_path.startswith(("http://", "https://")):
        return url_path
    return f"{_BASE_URL}{url_path if url_path.startswith('/') else '/' + url_path}"


def _salary(offer: dict[str, Any]) -> Salary:
    if offer.get("salary_hidden") is True:
        return Salary()
    salary_from = offer.get("salary_display_from")
    salary_to = offer.get("salary_display_to")
    if salary_from is None and salary_to is None:
        return Salary()
    return Salary(
        from_=salary_from if isinstance(salary_from, int) else None,
        to=salary_to if isinstance(salary_to, int) else None,
        currency=offer.get("salary_currency") if _nonempty(offer.get("salary_currency")) else None,
    )


def _skills(offer: dict[str, Any]) -> list[str]:
    skills = offer.get("skills_objects")
    if not isinstance(skills, list):
        return []
    names: list[str] = []
    for item in skills:
        name = item.get("name") if isinstance(item, dict) else None
        if _nonempty(name):
            names.append(name.strip())
    return names


def _labels(offer: dict[str, Any]) -> list[str]:
    items = offer.get("location_items")
    if not isinstance(items, list):
        return []
    labels: list[str] = []
    for item in items:
        label = item.get("label") if isinstance(item, dict) else None
        if _nonempty(label) and label.strip() not in labels:
            labels.append(label.strip())
    return labels


def _location(offer: dict[str, Any]) -> str | None:
    return ", ".join(_labels(offer)) or None


def _enriched_description(offer: dict[str, Any]) -> str:
    """HTML-описание + строка стека и локации — полезно скорингу (data-model.md).

    Оригинальный HTML остаётся в raw['offer']['offer_description'] (S3); enrichment
    попадает в очищаемый description_raw → description_text.
    """
    parts: list[str] = []
    raw = offer.get("offer_description")
    if _nonempty(raw):
        parts.append(raw)
    skills = _skills(offer)
    if skills:
        parts.append(f"Стек: {', '.join(skills)}")
    location = _location(offer)
    if location:
        parts.append(f"Локация: {location}")
    return "\n".join(parts)
