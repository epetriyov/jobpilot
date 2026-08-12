"""Авторизация MCP по общему секрету `MCP_AUTH_TOKEN` (спека 006, US7, MCP3, [P-C1]).

Двойная защита (research §4): сетевая изоляция (stdio через SSH-туннель, наружу
порт не публикуется) + обязательный токен. Клиент передаёт токен полем `auth_token`
в аргументах вызова; middleware сверяет его и **удаляет** до передачи в инструмент,
поэтому в схему самого инструмента токен не попадает, а сам инструмент его не видит.

Отказ (нет токена / неверный) происходит ДО вызова инструмента — `call_next` не
вызывается (MCP3).
"""

from __future__ import annotations

import hmac
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

__all__ = ["AUTH_ARG", "AuthError", "AuthGuard", "TokenAuthMiddleware"]

# Зарезервированное имя аргумента для токена (удаляется до вызова инструмента).
AUTH_ARG = "auth_token"


class AuthError(Exception):
    """Нет токена или он неверный — вызов отклонён до инструмента (MCP3)."""


class AuthGuard:
    """Сверка предъявленного токена с ожидаемым (constant-time).

    Пустой ожидаемый токен — ошибка конфигурации: сервер не должен стартовать без
    секрета (иначе «авторизация» вырождается в пропуск всех). Constitution IV.
    """

    def __init__(self, expected: str) -> None:
        if not expected:
            raise ValueError("MCP_AUTH_TOKEN обязателен и не может быть пустым")
        self._expected = expected

    def verify(self, provided: str | None) -> None:
        if provided is None or not hmac.compare_digest(provided, self._expected):
            raise AuthError("MCP: отсутствует или неверный auth-токен")


class TokenAuthMiddleware(Middleware):
    """FastMCP middleware: проверяет `auth_token` в аргументах до вызова инструмента."""

    def __init__(self, guard: AuthGuard) -> None:
        self._guard = guard

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        args = dict(context.message.arguments or {})
        token = args.pop(AUTH_ARG, None)
        self._guard.verify(token)  # AuthError → инструмент не вызывается (MCP3)
        context.message.arguments = args
        return await call_next(context)
