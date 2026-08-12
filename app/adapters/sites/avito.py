"""Avito career — по-сайтовый адаптер лёгкой волны (SSR-HTML, httpx).

career.avito.com/vacancies/ отдаёт список вакансий прямо в исходном HTML (Bitrix
SSR, без анти-бота — в отличие от маркетплейса avito.ru). Карточка списка:

    <div class="vacancies-section__item" data-vacancy-section="…" data-vacancy-team="…"
         data-vacancy-geo="…">
      <a class="vacancies-section__item-name" href="/vacancies/<dept>/<id>/">Title</a>
      <div class="vacancies-section__item-cities">Город[, …]</div>
    </div>

Чистая parse_avito(html) → list[Vacancy] (без I/O, покрыта golden). Портал = один
работодатель → company/site_name = «avito». Зарплата в списке не публикуется
(Salary пуст). external_id — id из URL карточки (стабильный ключ), не data-vacancy-id.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

SITE_NAME = "avito"
_BASE_URL = "https://career.avito.com"
_LIST_URL = f"{_BASE_URL}/vacancies/"

# id из URL карточки /vacancies/<dept-slug>/<id>/ — стабильный ключ (не data-vacancy-id).
_CARD_ID = re.compile(r"/vacancies/[^/]+/(\d+)")


def _attr(node: Tag, name: str) -> str:
    value = node.get(name)
    return value.strip() if isinstance(value, str) else ""


def parse_avito(payload: str) -> list[Vacancy]:
    """HTML списка career.avito.com/vacancies/ → Vacancy[] (дедуп по external_id)."""
    soup = BeautifulSoup(payload, "html.parser")
    vacancies: list[Vacancy] = []
    seen: set[str] = set()

    for item in soup.select("div.vacancies-section__item"):
        name = item.select_one("a.vacancies-section__item-name")
        if name is None:
            continue
        href = name.get("href")
        if not isinstance(href, str):
            continue
        match = _CARD_ID.search(href)
        if match is None:
            continue
        external_id = match.group(1)
        if external_id in seen:
            continue
        seen.add(external_id)

        title = name.get_text(strip=True)
        if not title:
            continue

        cities = item.select_one("div.vacancies-section__item-cities")
        location = (
            cities.get_text(strip=True) if cities is not None else _attr(item, "data-vacancy-geo")
        )

        # описание из списка = департамент/команда (полное описание — на карточке)
        section, team = _attr(item, "data-vacancy-section"), _attr(item, "data-vacancy-team")
        parts = [p for p in (section, team) if p]

        vacancies.append(
            Vacancy.create(
                source_ref=SourceRef(
                    source=Source.SITE, site_name=SITE_NAME, external_id=external_id
                ),
                title=title,
                company=SITE_NAME,
                url=f"{_BASE_URL}{href.split('?', 1)[0]}",  # абсолютный, без трекинга
                description_raw=" · ".join(parts),
                location=location or None,
            )
        )
    return vacancies


def avito_factory(settings: Settings, escalate: EscalateFn | None) -> SiteAdapter:
    """SiteAdapter для Avito career поверх вежливого HttpTransport (SSR-HTML)."""
    transport = HttpTransport(
        url=_LIST_URL,
        user_agent=settings.sites_user_agent,
        rate_limit_sec=settings.sites_rate_limit_sec,
        timeout_sec=settings.sites_timeout_sec,
        robots_respect=settings.sites_robots_respect,
    )
    return SiteAdapter(
        site_name=SITE_NAME,
        transport=transport,
        parse_fn=parse_avito,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
