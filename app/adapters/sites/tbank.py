"""Адаптер карьерного портала Т-Банк (лёгкая волна, JSON POST).

Т-Банк отдаёт список вакансий публичным JSON-эндпоинтом
`POST https://www.tbank.ru/pfpjobs/papi/getVacancies` (SPA career.tbank.ru).
Транспорт — общий HttpTransport (POST + json_body); ядро — чистая функция
`parse_tbank(payload) -> list[Vacancy]` (без I/O, под golden). Домен Sourcing
не меняется (DOMAIN.md §5): портал = новый адаптер + маппинг карточки в Vacancy.

Маппинг карточки (data-model.md §маппинг):
  external_id  ← urlSlug (uuid вакансии)
  title        ← title
  company      ← имя портала «tbank» (портал = один работодатель)
  url          ← https://www.tbank.ru/career/{categorySlug}/vacancy/{seoSlug}/{urlSlug}/
                 (формат подтверждён по career-sitemap, HTTP 200; без query/utm)
  location     ← subtitle (город); при пустом — первый city из cities
  salary       ← salary.amount («от X [до Y] ₽») → Salary(from?, to?, RUR)
  description  ← shortDescription + грейд/формат-теги (tags)

Заметка по телу POST (открытый пункт для system-architect):
  Эндпоинт живой и НЕ анти-бот — на невалидное тело отвечает структурированным
  JSON `{"resultCode":"INTERNAL_ERROR", "errorMessage":"...источник ... не валидный"}`
  (HTTP 503), а не капчей/стеной. getVacancies требует валидный `source` в теле:
  он выдаётся компаньон-вызовом (getSources/getFilters) — на спайке 2026-08-12
  перебор очевидных значений (it / back_office / tcareer_* / group-uuid) не прошёл
  серверную валидацию. Тело ниже кодирует подтверждённую структуру (source +
  pagination.offset); значение `source` нужно зафиксировать живым XHR-спайком в
  браузере до активации адаптера (SITES_ACTIVE). Golden от этого не зависит:
  парсер тестируется на записанной структуре ответа (транспорт ↔ парсер).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy

_SITE = "tbank"
_BASE = "https://www.tbank.ru"
_ENDPOINT = f"{_BASE}/pfpjobs/papi/getVacancies"
_PAGE_LIMIT = 100
# Открытый пункт: реальное значение `source` подтвердить браузерным XHR-спайком.
_REQUEST_SOURCE = "it"

# Сегмент раздела в URL карточки — карта фронта career.tbank.ru
# (ow = {BACK_OFFICE:"back-office", IT:"it", SERVICE:"service"}).
_CATEGORY_SLUGS = {
    "it": "it",
    "back_office": "back-office",
    "backoffice": "back-office",
    "service": "service",
    "publisher": "publisher",
}

# «от 400 000 ₽», «от 250 000 до 350 000 ₽» (пробелы: обычный/NBSP/narrow-NBSP).
_DIGITS = r"[\d\s  ]+?"
_SALARY = re.compile(
    rf"от\s+({_DIGITS})(?:\s*до\s+({_DIGITS}))?\s*(₽|руб\.?|р\.|rub|rur)",
    re.IGNORECASE,
)


def parse_tbank(payload: str) -> list[Vacancy]:
    """JSON ответа getVacancies → список Vacancy (дедуп по external_id=urlSlug)."""
    data = json.loads(payload)
    inner = data.get("payload") if isinstance(data, dict) else None
    cards = (inner or {}).get("vacancies") if isinstance(inner, dict) else None
    by_id: dict[str, Vacancy] = {}
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        external_id = _text(card.get("urlSlug"))
        title = _text(card.get("title"))
        seo_slug = _text(card.get("seoSlug")).strip("/")
        # completeness 100% ([S-C7]): без стабильного id / заголовка / seo-пути —
        # карточку не пропускаем в домен (иначе битый URL или дубль по хешу).
        if not external_id or not title or not seo_slug:
            continue
        if external_id in by_id:
            continue
        by_id[external_id] = Vacancy.create(
            source_ref=SourceRef(source=Source.SITE, site_name=_SITE, external_id=external_id),
            title=title,
            company=_SITE,
            url=_card_url(card.get("category"), seo_slug, external_id),
            description_raw=_description(card),
            salary=_salary(card.get("salary")),
            location=_location(card),
        )
    return list(by_id.values())


def tbank_factory(settings: Settings, escalate: EscalateFn | None) -> SiteAdapter:
    """SiteAdapter Т-Банка: HttpTransport(POST JSON) → parse_tbank → EM-фильтр."""
    transport = HttpTransport(
        url=_ENDPOINT,
        method="POST",
        json_body={
            "source": _REQUEST_SOURCE,
            "pagination": {"offset": 0, "limit": _PAGE_LIMIT},
        },
        user_agent=settings.sites_user_agent,
        rate_limit_sec=settings.sites_rate_limit_sec,
        timeout_sec=settings.sites_timeout_sec,
        robots_respect=settings.sites_robots_respect,
    )
    return SiteAdapter(
        site_name=_SITE,
        transport=transport,
        parse_fn=parse_tbank,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )


def _card_url(category: Any, seo_slug: str, external_id: str) -> str:
    segment = _category_slug(category)
    url = f"{_BASE}/career/{segment}/vacancy/{seo_slug}/{external_id}/"
    return _strip_tracking(url)


def _category_slug(category: Any) -> str:
    key = _text(category).lower()
    if not key:
        return "vacancies"
    return _CATEGORY_SLUGS.get(key, key.replace("_", "-"))


def _strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _description(card: dict[str, Any]) -> str:
    parts = [_text(card.get("shortDescription"))]
    parts.extend(_tag_label(tag) for tag in card.get("tags") or [])
    return "\n".join(p for p in parts if p)


def _tag_label(tag: Any) -> str:
    if isinstance(tag, str):
        return tag.strip()
    if isinstance(tag, dict):
        for key in ("name", "title", "label", "value", "text"):
            label = _text(tag.get(key))
            if label:
                return label
    return ""


def _location(card: dict[str, Any]) -> str | None:
    subtitle = _text(card.get("subtitle"))
    if subtitle:
        return subtitle
    for city in card.get("cities") or []:
        if isinstance(city, str) and city.strip():
            return city.strip()
        if isinstance(city, dict):
            name = _text(city.get("name") or city.get("title"))
            if name:
                return name
    return None


def _salary(raw: Any) -> Salary:
    if isinstance(raw, dict):
        amount = _text(raw.get("amount"))
    elif isinstance(raw, str):
        amount = raw.strip()
    else:
        amount = ""
    match = _SALARY.search(amount)
    if not match:
        return Salary()
    to = _to_int(match.group(2)) if match.group(2) else None
    return Salary(from_=_to_int(match.group(1)), to=to, currency="RUR")


def _to_int(value: str) -> int:
    return int(re.sub(r"\D", "", value))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__: Sequence[str] = ["parse_tbank", "tbank_factory"]
