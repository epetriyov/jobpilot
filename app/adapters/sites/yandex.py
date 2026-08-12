"""Адаптер портала вакансий Яндекса (лёгкая волна, SSR-HTML).

Зонд 2026-08-12 (честный GET, UA `JobPilot/0.1 (jobpilot-owner)`):
`https://yandex.ru/jobs/vacancies` отдаёт вакансии прямо в исходном HTML (SSR),
внутреннего JSON-эндпоинта нет (`/jobs/api/vacancies` → 404 HTML). robots.txt
(`User-agent: *`) раздел `/jobs/vacancies` НЕ запрещает (Disallow только на
`/jobs/skill-diagnostic/private/*`). Зарплата в списке не публикуется. Поэтому
транспорт — `HttpTransport` (GET), парсер — над SSR-HTML.

Чистое ядро `parse_yandex(html) -> list[Vacancy]` без I/O тестируется golden-файлом
([S-C7]/[S-C8]); транспорт отделён, чтобы смена HTML→JSON не ломала golden. Маппинг —
data-model.md §маппинг: company='yandex' (портал = один работодатель), url без
tracking, external_id — числовой id из хвоста url (иначе slug), salary опциональна.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import structlog
from bs4 import BeautifulSoup, Tag

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

log = structlog.get_logger("adapters.sites.yandex")

SITE_NAME = "yandex"
COMPANY = "yandex"  # портал = один работодатель (data-model.md §маппинг)
BASE_URL = "https://yandex.ru"
LIST_URL = "https://yandex.ru/jobs/vacancies"

# Классы SSR-вёрстки Яндекса содержат хешированный суффикс (CSS-modules), поэтому
# матчим по стабильному префиксу, а не по полному имени класса.
_WRAPPER = re.compile(r"VacancySnippet_wrapper")
_TITLE_LINK = re.compile(r"VacancySnippet_titleLink")
_CITY_HREF = re.compile(r"/jobs/vacancies/city_")
_NUMERIC_TAIL = re.compile(r"-(\d+)$")
# трекинг-параметры, вычищаемые из url (robots Clean-Param + типовой набор)
_TRACKING_PREFIXES = ("utm_", "yclid", "_openstat", "gclid", "clid", "from")


def _clean_url(href: str) -> str:
    """Абсолютный url карточки без tracking-хвоста (data-model.md §маппинг)."""
    parts = urlsplit(urljoin(BASE_URL, href))
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _external_id(url: str) -> str:
    """Стабильный ключ карточки: числовой id из хвоста slug, иначе сам slug."""
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    m = _NUMERIC_TAIL.search(slug)
    return m.group(1) if m else slug


def _location(card: Tag) -> str | None:
    city = card.find("a", href=_CITY_HREF)
    if city is None:
        return None
    text = str(city.get_text(strip=True))
    return text or None


def _description(card: Tag) -> str:
    p = card.find("p")
    return str(p.get_text(" ", strip=True)) if p is not None else ""


def parse_yandex(payload: str) -> list[Vacancy]:
    """HTML списка `/jobs/vacancies` → список Vacancy (дедуп по external_id).

    Пустой/битый payload или изменившаяся вёрстка без карточек → []. Без I/O.
    """
    soup = BeautifulSoup(payload, "html.parser")
    vacancies: list[Vacancy] = []
    seen: set[str] = set()
    for card in soup.find_all(class_=_WRAPPER):
        link = card.find("a", class_=_TITLE_LINK)
        if link is None:
            continue
        title = str(link.get_text(strip=True))
        href = link.get("href")
        if not title or not href:
            continue
        url = _clean_url(str(href))
        external_id = _external_id(url)
        if external_id in seen:
            continue
        seen.add(external_id)
        vacancies.append(
            Vacancy.create(
                source_ref=SourceRef(
                    source=Source.SITE, site_name=SITE_NAME, external_id=external_id
                ),
                title=title,
                company=COMPANY,
                url=url,
                description_raw=_description(card),
                location=_location(card),
            )
        )
    return vacancies


def yandex_factory(settings: Settings, escalate: EscalateFn | None) -> SiteAdapter:
    """Собрать SiteAdapter Яндекса на HttpTransport (GET списка вакансий)."""
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
        parse_fn=parse_yandex,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
