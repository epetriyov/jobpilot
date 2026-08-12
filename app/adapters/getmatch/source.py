"""GetMatchSource — вакансии из публичного JSON GetMatch `GET /api/offers` (этап 4).

Лёгкий httpx-адаптер за `VacancySourcePort` (без Playwright/Chromium, research §4):
пагинация `offset += limit` до `meta.total`, вежливый доступ (1 rps, честный
User-Agent, таймаут + ретрай на 5xx), чистый маппинг делегирован
`parse_getmatch_offers`. Домен Sourcing не меняется.

⚠️ robots.txt GetMatch содержит `Disallow: /api/` (research §2, scraping-risks.md 🟡):
источник **off-by-default**, включается только явным owner-approval после canary
(constitution VI). Обход анти-бота/капчи/блока НЕ проектируется (S5, constitution IV):
401/403/429/капча → эскалация владельцу + `GetMatchFetchError` (коллектор изолирует,
job_run.status=partial, S4). Робот-запрет здесь НЕ энфорсится кодом — это осознанное
решение владельца по ToS, зафиксированное при включении источника.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
import structlog

from app.adapters.getmatch.parser import parse_getmatch_offers, read_meta
from app.domain.sourcing import Vacancy

log = structlog.get_logger("adapters.getmatch")

SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]
EscalateFn = Callable[[str], Awaitable[None]]

# Маркеры анти-бот-стены в теле ответа (GetMatch «тихо» включил защиту).
_ANTI_BOT_MARKERS = (
    "captcha",
    "qrator",
    "cf-browser-verification",
    "attention required",
    "checking your browser",
    "just a moment",
)
_ANTI_BOT_STATUSES = frozenset({401, 403, 429})
# Жёсткая крышка страниц — защита от бесконечной пагинации при кривом meta.total.
_MAX_PAGES = 100

# Последний момент запроса на хост — общий на процесс (1 rps суммарно).
_last_request_at: dict[str, float] = {}


class GetMatchTransportError(Exception):
    """Сбой добычи страницы; kind — метка классификации (наблюдаемость)."""

    kind = "transport"


class GetMatchHttpError(GetMatchTransportError):
    """5xx/сетевой сбой после ретраев или не-JSON тело (доступ недоступен, S4)."""

    kind = "http_error"


class GetMatchEmptyError(GetMatchTransportError):
    """Пустой ответ `/api/offers` — трактуем как сбой доступа (S4)."""

    kind = "empty"


class GetMatchAntiBotError(GetMatchTransportError):
    """Капча/анти-бот-стена/логин-стена. S5: обход НЕ реализуется — эскалация."""

    kind = "anti_bot"


class GetMatchFetchError(Exception):
    """Сбой сбора источника GetMatch; коллектор изолирует (S4): job_run=partial."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"getmatch fetch failed ({kind})")
        self.kind = kind


class GetMatchPageFetcher(Protocol):
    """Добывает сырой JSON одной страницы `/api/offers?offset&limit`."""

    async def fetch_page(self, *, offset: int, limit: int) -> str: ...


class GetMatchApiClient:
    """Вежливый httpx-транспорт `/api/offers`: rate-limit, честный UA, ретраи 5xx.

    Классифицирует ответ: 401/403/429/капча-маркер → анти-бот (S5, обход НЕ строим),
    5xx после ретраев/не-JSON → http_error, пустое тело → empty. Не парсит offers —
    отдаёт валидную JSON-строку страницы.
    """

    def __init__(
        self,
        *,
        api_url: str,
        user_agent: str,
        pause_sec: float,
        timeout_sec: float,
        client: httpx.AsyncClient | None = None,
        sleep: SleepFn = asyncio.sleep,
        clock: ClockFn = time.monotonic,
        max_retries: int = 2,
    ) -> None:
        self._api_url = api_url
        self._user_agent = user_agent
        self._pause_sec = pause_sec
        self._timeout_sec = timeout_sec
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._max_retries = max_retries

    async def fetch_page(self, *, offset: int, limit: int) -> str:
        client = self._client or httpx.AsyncClient()
        try:
            await self._respect_rate_limit()
            return await self._request(client, offset=offset, limit=limit)
        finally:
            if self._client is None:
                await client.aclose()

    @property
    def _host(self) -> str:
        return httpx.URL(self._api_url).host

    async def _respect_rate_limit(self) -> None:
        last = _last_request_at.get(self._host)
        now = self._clock()
        if last is not None:
            elapsed = now - last
            if elapsed < self._pause_sec:
                await self._sleep(self._pause_sec - elapsed)
        _last_request_at[self._host] = self._clock()

    async def _request(self, client: httpx.AsyncClient, *, offset: int, limit: int) -> str:
        headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        params = {"offset": str(offset), "limit": str(limit)}
        last_status: int | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await client.get(
                    self._api_url, params=params, headers=headers, timeout=self._timeout_sec
                )
            except httpx.HTTPError as exc:
                last_status = None
                log.warning("getmatch_http_error", offset=offset, attempt=attempt, error=str(exc))
                continue
            if resp.status_code in _ANTI_BOT_STATUSES:
                raise GetMatchAntiBotError()
            if resp.status_code >= 500:
                last_status = resp.status_code
                continue
            body = resp.text
            if _looks_like_anti_bot(body):
                raise GetMatchAntiBotError()
            if not body.strip():
                raise GetMatchEmptyError()
            _ensure_json(body)
            return body
        raise GetMatchHttpError(f"http status {last_status}" if last_status else "http error")


class GetMatchSource:
    """`VacancySourcePort` поверх (`GetMatchApiClient` → `parse_getmatch_offers`)."""

    name = "getmatch"

    def __init__(
        self,
        *,
        client: GetMatchPageFetcher,
        page_limit: int,
        escalate: EscalateFn | None = None,
        max_pages: int = _MAX_PAGES,
    ) -> None:
        self._client = client
        self._page_limit = page_limit
        self._escalate = escalate
        self._max_pages = max_pages

    async def fetch(self) -> list[Vacancy]:
        by_ref: dict[str, Vacancy] = {}
        offset = 0
        pages = 0
        while pages < self._max_pages:
            try:
                raw = await self._client.fetch_page(offset=offset, limit=self._page_limit)
            except GetMatchAntiBotError as exc:
                await self._escalate_anti_bot()
                raise GetMatchFetchError("anti_bot") from exc
            except GetMatchTransportError as exc:
                if not by_ref:
                    log.warning("getmatch_fetch_failed", offset=offset, kind=exc.kind)
                    raise GetMatchFetchError(exc.kind) from exc
                # сбой поздней страницы: уже собранное отдаётся (S4, edge case spec)
                log.warning("getmatch_page_failed", offset=offset, kind=exc.kind)
                break

            for vacancy in parse_getmatch_offers(raw):
                by_ref.setdefault(vacancy.source_ref.as_key(), vacancy)

            meta = read_meta(raw)
            pages += 1
            offset += self._page_limit
            if meta.offer_count == 0 or meta.total is None or offset >= meta.total:
                break

        log.info("getmatch_fetched", pages=pages, vacancies=len(by_ref))
        return list(by_ref.values())

    async def _escalate_anti_bot(self) -> None:
        log.warning("getmatch_anti_bot", source="getmatch")
        if self._escalate is not None:
            await self._escalate(
                "⛔ Источник getmatch включил анти-бот/капчу/блок. "
                "Обход не выполняется (S5) — сбор с GetMatch остановлен."
            )


def _looks_like_anti_bot(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _ANTI_BOT_MARKERS)


def _ensure_json(body: str) -> None:
    try:
        json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GetMatchHttpError("non-json body") from exc
