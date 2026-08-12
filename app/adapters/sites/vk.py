"""VK career-portal адаптер (team.vk.company) — лёгкая волна, SSR-HTML.

Портал VK Team отдаёт список вакансий сервер-рендером: страница `/vacancy/`
несёт встроенный `__NEXT_DATA__` (Next.js) с массивом `initialVacancies`.
Парсим встроенный JSON, а не CSS-классы вёрстки — он стабильнее к рестайлам
(research.md: «вакансии в исходном HTML»; предпочли чистый внутренний JSON).

Чистое ядро — `parse_vk(payload) -> list[Vacancy]` (без I/O, тестируется golden).
Транспорт (HttpTransport, честный UA + robots) отделён и собирается фабрикой.
Домен SOURCING не меняется (data-model.md §маппинг):
external_id = id карточки; company = «vk» (портал = один работодатель);
url без трекинга; salary в списке отсутствует → Salary(); location = город/формат.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from bs4 import BeautifulSoup

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

log = structlog.get_logger("adapters.sites.vk")

SITE_NAME = "vk"
LIST_URL = "https://team.vk.company/vacancy/"
_CARD_URL = "https://team.vk.company/vacancy/{id}/"


def _location(card: dict[str, Any]) -> str | None:
    """Город + формат занятости («Москва, Офисный») — как показывает SSR-карточка."""
    town = card.get("town") or {}
    parts = [str(town.get("name")).strip()] if town.get("name") else []
    work_format = card.get("work_format")
    if isinstance(work_format, str) and work_format.strip():
        parts.append(work_format.strip())
    return ", ".join(parts) if parts else None


def _description(card: dict[str, Any]) -> str:
    """Направление/краткое описание: подразделение + проф-область/специализация."""
    group = card.get("group") or {}
    prof_area = card.get("prof_area") or {}
    specialty = card.get("specialty") or {}
    bits = [str(v.get("name")).strip() for v in (group, prof_area, specialty) if v.get("name")]
    return " / ".join(dict.fromkeys(bits))  # порядок, без дублей


def _extract_vacancies(payload: str) -> list[dict[str, Any]]:
    """Достать initialVacancies из встроенного __NEXT_DATA__; иначе — пусто."""
    soup = BeautifulSoup(payload, "html.parser")
    node = soup.find("script", id="__NEXT_DATA__")
    if node is None or not node.string:
        return []
    try:
        data = json.loads(node.string)
    except json.JSONDecodeError:
        log.warning("vk_next_data_decode_failed")
        return []
    vacancies = (data.get("props", {}).get("pageProps", {}) or {}).get("initialVacancies")
    return vacancies if isinstance(vacancies, list) else []


def parse_vk(payload: str) -> list[Vacancy]:
    """SSR-страница VK Team → список Vacancy (дедуп по external_id).

    Пустой/непарсимый payload или отсутствие __NEXT_DATA__ → []. Карточки без
    id/title пропускаются (без них нет стабильного ключа/обязательного поля).
    """
    if not payload.strip():
        return []
    result: list[Vacancy] = []
    seen: set[str] = set()
    for card in _extract_vacancies(payload):
        if not isinstance(card, dict):
            continue
        raw_id = card.get("id")
        title = card.get("title")
        if raw_id is None or not isinstance(title, str) or not title.strip():
            continue
        external_id = str(raw_id)
        if external_id in seen:
            continue
        seen.add(external_id)
        result.append(
            Vacancy.create(
                source_ref=SourceRef(
                    source=Source.SITE, site_name=SITE_NAME, external_id=external_id
                ),
                title=title.strip(),
                company=SITE_NAME,  # портал = один работодатель (data-model §маппинг)
                url=_CARD_URL.format(id=external_id),  # без utm/трекинга
                description_raw=_description(card),
                location=_location(card),
                extra_raw={"card": card},
            )
        )
    return result


def vk_factory(settings: Settings, escalate: EscalateFn | None) -> SiteAdapter:
    """Собрать SiteAdapter VK поверх вежливого HttpTransport (честный UA + robots)."""
    transport = HttpTransport(
        url=LIST_URL,
        user_agent=settings.sites_user_agent,
        rate_limit_sec=settings.sites_rate_limit_sec,
        timeout_sec=settings.sites_timeout_sec,
        robots_respect=settings.sites_robots_respect,
    )
    return SiteAdapter(
        site_name=SITE_NAME,
        transport=transport,
        parse_fn=parse_vk,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
