"""Точка входа MCP-сервера JobPilot (этап 6F, research §4).

Транспорт stdio: сервер запускается на VPS и подключается к Claude Desktop через
SSH-туннель; наружу порт не публикуется (UFW только 22, constitution). Секрет
`MCP_AUTH_TOKEN` обязателен — без него сервер не стартует (MCP3). Read-инструменты
ходят под ролью `mcp_ro` (`MCP_DB_DSN`), write — под основной ролью (MCP4).

Запуск: `python -m app.runtime.mcp_server` (compose profile `mcp`).
"""

from __future__ import annotations

import structlog
from aiogram import Bot

from app.adapters.persistence.database import make_engine, make_session_factory
from app.config import ConfigError, Settings
from app.mcp import build_mcp_server
from app.obs.logging import configure_logging
from app.runtime.composition import Services
from app.runtime.mcp_backend import ServicesMcpBackend

log = structlog.get_logger("runtime.mcp_server")


def _read_dsn(settings: Settings) -> str:
    """DSN read-роли (mcp_ro) или фолбэк на основной пул (dev/тесты)."""
    if settings.mcp_db_dsn is not None:
        return settings.mcp_db_dsn.get_secret_value()
    log.warning("mcp_ro_dsn_missing", reason="MCP_DB_DSN не задан — reads под основной ролью")
    return settings.postgres_dsn.get_secret_value()


def build_server(settings: Settings, bot: Bot):  # type: ignore[no-untyped-def]
    """Собрать FastMCP-сервер из настроек (вынесено для тестируемости)."""
    if settings.mcp_auth_token is None:
        raise ConfigError("MCP включён, но MCP_AUTH_TOKEN не задан (обязателен, MCP3)")
    services = Services(settings, bot)
    read_factory = make_session_factory(make_engine(_read_dsn(settings)))
    backend = ServicesMcpBackend(services=services, read_session_factory=read_factory)
    return build_mcp_server(backend, settings.mcp_auth_token.get_secret_value())


def main() -> None:
    settings = Settings.load()
    configure_logging(secret_values=settings.secret_values())
    bot = Bot(token=settings.telegram_api_token.get_secret_value())
    server = build_server(settings, bot)
    log.info("mcp_server_starting", transport=settings.mcp_transport)
    server.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
