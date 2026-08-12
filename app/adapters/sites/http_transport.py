"""HttpTransport — вежливый httpx-транспорт лёгкой волны (SSR-HTML / публичный JSON).

Инкапсулирует кросс-сайтовую механику доступа (FR-006, [S-C10]): rate-limit
(≥ rate_limit_sec между запросами к одному хосту), честный User-Agent, таймаут,
ретраи на 5xx, проверку robots.txt целевого пути. Классифицирует ответ:
403/429/капча-маркер → анти-бот (S5, обход НЕ строим), 5xx → сбой доступа,
пустое тело → сбой. Домен/парсер не трогает — отдаёт сырой текст payload.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from app.adapters.sites.transport import (
    AntiBotError,
    EmptyResponseError,
    HttpStatusError,
    RobotsDisallowedError,
)

log = structlog.get_logger("adapters.sites.http")

# Маркеры анти-бот-стены в теле ответа (лёгкий сайт «тихо» включил защиту, R-2).
_ANTI_BOT_MARKERS = (
    "captcha",
    "qrator",
    "cf-browser-verification",
    "attention required",
    "checking your browser",
    "just a moment",
)
_ANTI_BOT_STATUSES = frozenset({401, 403, 429})

SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]

# Последний момент запроса на хост — общий на процесс: несколько адаптеров к
# одному порталу не «складывают» частоту сверх лимита.
_last_request_at: dict[str, float] = {}


class HttpTransport:
    def __init__(
        self,
        *,
        url: str,
        method: str = "GET",
        json_body: dict[str, object] | None = None,
        user_agent: str,
        rate_limit_sec: float,
        timeout_sec: float,
        robots_respect: bool = True,
        client: httpx.AsyncClient | None = None,
        sleep: SleepFn = asyncio.sleep,
        clock: ClockFn = time.monotonic,
        max_retries: int = 2,
    ) -> None:
        self._url = url
        self._method = method.upper()
        self._json_body = json_body
        self._user_agent = user_agent
        self._rate_limit_sec = rate_limit_sec
        self._timeout_sec = timeout_sec
        self._robots_respect = robots_respect
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._max_retries = max_retries
        self._robots_checked = False

    async def fetch(self) -> str:
        client = self._client or httpx.AsyncClient()
        try:
            if self._robots_respect:
                await self._check_robots(client)
            await self._respect_rate_limit()
            return await self._request(client)
        finally:
            if self._client is None:
                await client.aclose()

    @property
    def _host(self) -> str:
        return httpx.URL(self._url).host

    async def _respect_rate_limit(self) -> None:
        last = _last_request_at.get(self._host)
        now = self._clock()
        if last is not None:
            elapsed = now - last
            if elapsed < self._rate_limit_sec:
                await self._sleep(self._rate_limit_sec - elapsed)
        _last_request_at[self._host] = self._clock()

    async def _check_robots(self, client: httpx.AsyncClient) -> None:
        if self._robots_checked:
            return
        robots_url = httpx.URL(self._url).copy_with(path="/robots.txt", query=None)
        try:
            resp = await client.get(str(robots_url), timeout=self._timeout_sec)
        except httpx.HTTPError:
            self._robots_checked = True  # robots недоступен — не блокируем (best-effort)
            return
        if resp.status_code == 200 and resp.text:
            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            if not parser.can_fetch(self._user_agent, self._url):
                raise RobotsDisallowedError(
                    f"robots.txt запрещает {self._url} для UA {self._user_agent}"
                )
        self._robots_checked = True

    async def _request(self, client: httpx.AsyncClient) -> str:
        headers = {"User-Agent": self._user_agent}
        last_status: int | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await client.request(
                    self._method,
                    self._url,
                    json=self._json_body if self._method == "POST" else None,
                    headers=headers,
                    timeout=self._timeout_sec,
                )
            except httpx.HTTPError as exc:
                last_status = None
                log.warning("site_http_error", url=self._url, attempt=attempt, error=str(exc))
                continue
            if resp.status_code in _ANTI_BOT_STATUSES:
                raise AntiBotError()
            if resp.status_code >= 500:
                last_status = resp.status_code
                continue
            body = resp.text
            if _looks_like_anti_bot(body):
                raise AntiBotError()
            if not body.strip():
                raise EmptyResponseError()
            return body
        raise HttpStatusError(last_status)


def _looks_like_anti_bot(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _ANTI_BOT_MARKERS)
