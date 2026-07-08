"""Точка входа бота (long polling). Тонкий композиционный корень."""

from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.bot.middleware import OwnerOnlyMiddleware
from app.config import Settings
from app.obs.logging import configure_logging
from app.obs.telemetry import setup_telemetry

log = structlog.get_logger("bot")


async def main() -> None:
    settings = Settings.load()
    configure_logging(secret_values=settings.secret_values())
    setup_telemetry(
        service_name="jobpilot-bot",
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )

    bot = Bot(token=settings.telegram_api_token.get_secret_value())
    dp = Dispatcher()
    owner_only = OwnerOnlyMiddleware(owner_chat_id=settings.owner_chat_id)
    dp.message.middleware(owner_only)
    dp.include_router(router)

    log.info("bot_starting", dry_run=settings.dry_run)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
