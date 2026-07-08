"""Точка входа обработчика плановых задач (APScheduler, зона Europe/Moscow).

Планировщик работает в TZ_SCHEDULER; все метки времени в БД — UTC (PLAN.md §7).
На этапе 0 зарегистрирован единственный демонстрационный job (smoke) —
реальные задачи (дайджест 10:00, publish каждые 4 часа) добавляются с этапа 1.
"""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.obs.logging import configure_logging
from app.obs.telemetry import setup_telemetry

log = structlog.get_logger("worker")


async def main() -> None:
    settings = Settings.load()
    configure_logging(secret_values=settings.secret_values())
    setup_telemetry(
        service_name="jobpilot-worker", otlp_endpoint=settings.otel_exporter_otlp_endpoint
    )

    scheduler = AsyncIOScheduler(timezone=settings.tz_scheduler)
    # Демонстрационный тик; наполняется задачами с этапа 1.
    scheduler.start()
    log.info("worker_started", tz=settings.tz_scheduler, dry_run=settings.dry_run)

    stop = asyncio.Event()
    await stop.wait()


if __name__ == "__main__":
    asyncio.run(main())
