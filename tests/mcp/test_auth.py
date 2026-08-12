"""T6F-3 [P-C1] (MCP3): обязательный auth-токен, отказ до вызова инструмента."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.mcp.auth import AUTH_ARG, AuthError, AuthGuard, TokenAuthMiddleware


def _ctx(arguments: dict[str, Any] | None) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(arguments=arguments))


def test_empty_expected_token_rejected() -> None:
    with pytest.raises(ValueError):
        AuthGuard("")


def test_guard_accepts_correct_token() -> None:
    AuthGuard("s3cret").verify("s3cret")  # не бросает


@pytest.mark.parametrize("provided", [None, "", "wrong"])
def test_guard_rejects_bad_token(provided: str | None) -> None:
    with pytest.raises(AuthError):
        AuthGuard("s3cret").verify(provided)


async def test_middleware_denies_before_tool() -> None:
    mw = TokenAuthMiddleware(AuthGuard("s3cret"))
    called = False

    async def call_next(_ctx: Any) -> str:
        nonlocal called
        called = True
        return "reached-tool"

    with pytest.raises(AuthError):
        await mw.on_call_tool(_ctx({"x": 1}), call_next)  # без токена
    assert called is False


async def test_middleware_denies_wrong_token_before_tool() -> None:
    mw = TokenAuthMiddleware(AuthGuard("s3cret"))
    called = False

    async def call_next(_ctx: Any) -> str:
        nonlocal called
        called = True
        return "reached-tool"

    with pytest.raises(AuthError):
        await mw.on_call_tool(_ctx({"x": 1, AUTH_ARG: "nope"}), call_next)
    assert called is False


async def test_middleware_passes_and_strips_token() -> None:
    mw = TokenAuthMiddleware(AuthGuard("s3cret"))
    seen: dict[str, Any] = {}

    async def call_next(ctx: Any) -> str:
        seen["args"] = ctx.message.arguments
        return "ok"

    ctx = _ctx({"x": 1, AUTH_ARG: "s3cret"})
    result = await mw.on_call_tool(ctx, call_next)
    assert result == "ok"
    assert seen["args"] == {"x": 1}  # токен вырезан до инструмента
