"""Сборка FastMCP-сервера JobPilot (спека 006, US7, MCP1–MCP3, research §4).

Тонкий слой: сервер получает `McpBackend` (порт) и токен, регистрирует инструменты
из реестра (`app.ports.mcp.build_registry`) и вешает auth-middleware. Никаких
импортов persistence/SQLAlchemy здесь нет (MCP1) — вся работа с БД спрятана за портом
в композиционном корне (`app/runtime`).
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.tools import Tool

from app.mcp.auth import AuthGuard, TokenAuthMiddleware
from app.ports.mcp import AUTH_ARG_HINT, McpBackend, build_registry

__all__ = ["build_mcp_server"]


def build_mcp_server(backend: McpBackend, auth_token: str, *, name: str = "jobpilot") -> FastMCP:
    """Собрать FastMCP-сервер: auth-middleware + инструменты из реестра.

    Транспорт (stdio) выбирается на запуске (`server.run(transport=...)`) в
    композиционном корне — сам сервер транспортно-нейтрален.
    """
    guard = AuthGuard(auth_token)  # пустой токен → ValueError ещё до старта
    server: FastMCP = FastMCP(name=name)
    server.add_middleware(TokenAuthMiddleware(guard))
    for spec in build_registry(backend).specs:
        description = f"{spec.description}\n\n{AUTH_ARG_HINT}"
        server.add_tool(Tool.from_function(spec.handler, name=spec.name, description=description))
    return server
