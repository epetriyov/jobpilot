"""Контракт транспорта сайта и его ошибки (plan.md: транспорт↔парсер).

Транспорт добывает сырой payload (HTML/JSON-строку); чистый parse_<site> его
разбирает. Ошибки транспорта классифицированы, чтобы SiteAdapter отличал
анти-бот (S5 — эскалация, НЕ обход) от обычного сбоя доступа (S4).
"""

from __future__ import annotations

from typing import Protocol


class TransportError(Exception):
    """Базовый сбой транспорта; kind — метка для наблюдаемости/классификации."""

    kind = "transport"


class HttpStatusError(TransportError):
    """5xx/сетевой сбой после ретраев (доступ к порталу временно недоступен)."""

    kind = "http_error"

    def __init__(self, status: int | None = None) -> None:
        super().__init__(f"http status {status}" if status else "http error")
        self.status = status


class EmptyResponseError(TransportError):
    """Пустой ответ портала — трактуем как сбой доступа (S4)."""

    kind = "empty"


class AntiBotError(TransportError):
    """Капча/анти-бот-стена/логин-стена. S5: обход НЕ реализуется — эскалация."""

    kind = "anti_bot"


class RobotsDisallowedError(TransportError):
    """robots.txt запрещает целевой раздел → портал не запрашивается (guardrail)."""

    kind = "robots_disallowed"


class SiteTransport(Protocol):
    """Добывает сырой payload списка вакансий (httpx JSON/HTML | Playwright)."""

    async def fetch(self) -> str: ...
