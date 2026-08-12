"""MCP-сервер JobPilot (спека 006, US7): тонкий слой поверх use cases.

MCP1: этот пакет НЕ импортирует `app.adapters.persistence`/SQLAlchemy/`app.runtime` —
только порт `app.ports.mcp` и FastMCP. Композиция БД — в `app/runtime/mcp_server.py`.
"""

from app.mcp.auth import AuthError, AuthGuard, TokenAuthMiddleware
from app.mcp.server import build_mcp_server

__all__ = ["AuthError", "AuthGuard", "TokenAuthMiddleware", "build_mcp_server"]
