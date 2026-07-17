"""HhWebSource — рекомендации HH с сайта через Playwright (пересмотр 2026-07-15).

Парсинг HTML — чистая функция (offline-тесты на golden); Playwright лишь грузит DOM
по авторизованной сессии (сохранённый профиль). Капча/логин-стена → HhWebBlocked
→ эскалация владельцу, БЕЗ обхода (S5, constitution IV). 1 rps, честный User-Agent.
"""

from __future__ import annotations

import re
from typing import Literal

import structlog
from bs4 import BeautifulSoup, Tag

from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy

log = structlog.get_logger("adapters.hh.web")

_SALARY = re.compile(r"от\s+([\d\s ]+?)(?:\s+до\s+([\d\s ]+?))?\s*(?:₽|руб|р\.)", re.IGNORECASE)


class HhWebBlocked(Exception):
    """Логин-стена или капча — не обходим, эскалируем ([S-C4b], S5)."""


def detect_block(html: str) -> Literal["captcha", "login", "antibot"] | None:
    lowered = html.lower()
    if 'data-qa="captcha"' in lowered or "не робот" in lowered or "captcha-wrapper" in lowered:
        return "captcha"
    # анти-бот/VPN-заглушка HH (реальная сигнатура 2026-07-17): страница «Ой…»
    # без карточек вакансий. Не обходим — эскалируем (S5, constitution IV).
    if "vpn-cheeck-support-code" in lowered or ("заблокирован" in lowered and "vpn" in lowered):
        return "antibot"
    if 'data-qa="account-login-form"' in lowered or "вход на hh.ru" in lowered:
        return "login"
    return None


def _text(node: Tag | None) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _salary(raw: str) -> Salary:
    m = _SALARY.search(raw)
    if not m:
        return Salary()
    to = int(re.sub(r"\D", "", m.group(2))) if m.group(2) else None
    return Salary(from_=int(re.sub(r"\D", "", m.group(1))), to=to, currency="RUR")


def parse_recommendations_html(html: str) -> list[Vacancy]:
    """HTML страницы рекомендаций → список Vacancy (пусто при смене структуры — [S-C2])."""
    soup = BeautifulSoup(html, "html.parser")
    vacancies: list[Vacancy] = []
    for card in soup.select('[data-qa="vacancy-serp__vacancy"]'):
        link = card.select_one('[data-qa="serp-item__title"]')
        if link is None or not link.get("href"):
            continue
        url = str(link["href"])
        id_match = re.search(r"/vacancy/(\d+)", url)
        if id_match is None:
            continue
        snippet = card.select_one('[data-qa="vacancy-serp__vacancy_snippet_responsibility"]')
        vacancies.append(
            Vacancy.create(
                source_ref=SourceRef(source=Source.HH, external_id=id_match.group(1)),
                title=_text(link),
                company=_text(card.select_one('[data-qa="vacancy-serp__vacancy-employer"]')),
                url=url,
                description_raw=str(snippet) if snippet else "",
                salary=_salary(_text(card.select_one('[data-qa*="compensation"]'))),
                location=_text(card.select_one('[data-qa="vacancy-serp__vacancy-address"]'))
                or None,
            )
        )
    return vacancies


class HhWebSource:
    """VacancySourcePort: грузит рекомендации Playwright'ом, парсит чистой функцией."""

    name = "hh"

    def __init__(self, *, page_loader: object, url: str) -> None:
        # page_loader.load(url) -> html; реальный — Playwright, тесты — фейк/golden
        self._loader = page_loader
        self._url = url

    async def fetch(self) -> list[Vacancy]:
        html = await self._loader.load(self._url)  # type: ignore[attr-defined]
        block = detect_block(html)
        if block is not None:
            log.warning("hh_web_blocked", kind=block)
            raise HhWebBlocked(block)  # → SourceFetchFailed (S4), эскалация владельцу
        vacancies = parse_recommendations_html(html)
        log.info("hh_web_fetched", count=len(vacancies))
        return vacancies
