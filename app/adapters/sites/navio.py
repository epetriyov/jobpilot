"""Адаптер карьерного портала Navio (navio.auto) — лёгкая волна, встроенный JSON.

Зонд 2026-08-13 (честный GET, UA `JobPilot/1.0 (+owner-contact)`):
`https://navio.auto/vacancies` отдаёт 200/~338КБ. Сайт на Gatsby: страница
одновременно несёт SSR-разметку списка И богатый встроенный JSON состояния в
`<script id="gatsby-script-loader">` — присваивание `window.pageData={...}` с
массивом `result.serverData.vacancies`. robots.txt пуст/разрешает; ld+json
JobPosting нет; зарплата в списке не публикуется.

Парсим встроенный JSON (как VK Team), а не CSS-классы вёрстки — он богаче (id,
город, тип занятости, направление, опыт) и стабильнее к рестайлам. Чистое ядро
`parse_navio(payload) -> list[Vacancy]` без I/O тестируется golden-файлом;
транспорт (HttpTransport GET, честный UA + robots) отделён, чтобы смена
HTML→JSON не ломала golden.

Маппинг (data-model.md §маппинг): company='navio' (портал = один работодатель —
это карьерный сайт самой компании Navio, не агрегатор); external_id = строковый
id карточки; url = каноничный `/vacancies/{id}` без трекинга; location = город +
тип занятости; description — направление/область/опыт (поле `about` одинаково для
всех карточек — это описание компании, не вакансии, поэтому в описание не идёт).
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from bs4 import BeautifulSoup

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.http_transport import HttpTransport
from app.config import Settings
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

log = structlog.get_logger("adapters.sites.navio")

SITE_NAME = "navio"
COMPANY = "navio"  # портал = один работодатель (data-model.md §маппинг)
LIST_URL = "https://navio.auto/vacancies"
_CARD_URL = "https://navio.auto/vacancies/{id}"

# Присваивание состояния Gatsby в инлайн-скрипте: `window.pageData={...}`.
_PAGE_DATA_RE = re.compile(r"window\.pageData\s*=")


def _extract_json_object(text: str, start: int) -> str | None:
    """Сбалансированный срез JSON-объекта `{...}` от позиции start (учёт строк)."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_vacancies(payload: str) -> list[dict[str, Any]]:
    """Достать result.serverData.vacancies из window.pageData; иначе — пусто."""
    soup = BeautifulSoup(payload, "html.parser")
    node = soup.find("script", id="gatsby-script-loader")
    text = node.string if node is not None else None
    if not text:
        return []
    m = _PAGE_DATA_RE.search(text)
    if m is None:
        return []
    brace = text.find("{", m.end())
    if brace == -1:
        return []
    blob = _extract_json_object(text, brace)
    if blob is None:
        return []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        log.warning("navio_page_data_decode_failed")
        return []
    server = (data.get("result", {}) or {}).get("serverData", {}) or {}
    vacancies = server.get("vacancies")
    return vacancies if isinstance(vacancies, list) else []


def _location(card: dict[str, Any]) -> str | None:
    """Город + тип занятости («Видное, Офис») — как показывает карточка."""
    city = card.get("city") or {}
    parts = [str(city.get("text")).strip()] if city.get("text") else []
    job_type = card.get("jobType") or {}
    if job_type.get("text") and str(job_type["text"]).strip():
        parts.append(str(job_type["text"]).strip())
    return ", ".join(parts) if parts else None


def _description(card: dict[str, Any]) -> str:
    """Направление / область / требуемый опыт — краткий профиль вакансии."""
    direction = card.get("direction") or {}
    area = card.get("area") or {}
    experience = card.get("job_experience") or {}
    bits = [
        str(direction.get("header")).strip() if direction.get("header") else "",
        str(area.get("text")).strip() if area.get("text") else "",
        str(experience.get("text")).strip() if experience.get("text") else "",
    ]
    return " / ".join(dict.fromkeys(b for b in bits if b))  # порядок, без дублей


def parse_navio(payload: str) -> list[Vacancy]:
    """Страница `/vacancies` Navio → список Vacancy (дедуп по external_id).

    Пустой/непарсимый payload, отсутствие window.pageData или изменившаяся
    структура без карточек → []. Карточки без id/title пропускаются (без них нет
    стабильного ключа/обязательного поля). Без I/O.
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
                company=COMPANY,  # портал = один работодатель (data-model §маппинг)
                url=_CARD_URL.format(id=external_id),  # каноничный url без трекинга
                description_raw=_description(card),
                location=_location(card),
                extra_raw={"card": card},
            )
        )
    return result


def navio_factory(settings: Settings, escalate: EscalateFn | None) -> SiteAdapter:
    """Собрать SiteAdapter Navio на HttpTransport (GET списка вакансий)."""
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
        parse_fn=parse_navio,
        keywords=settings.sites_em_keywords,
        escalate=escalate,
    )
