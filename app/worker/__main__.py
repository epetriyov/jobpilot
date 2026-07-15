"""Точка входа обработчика плановых задач (APScheduler, зона Europe/Moscow).

Планировщик работает в TZ_SCHEDULER; все метки времени в БД — UTC (PLAN.md §7).
Этап 1: daily_digest (cron 10:00 МСК) и publish_resume (каждые 4 часа) — оба
через run_job (JobRun + root span + trace_id в логах).
"""

from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Settings
from app.obs.logging import configure_logging
from app.obs.telemetry import setup_telemetry
from app.runtime.composition import Services

log = structlog.get_logger("worker")


async def main() -> None:
    settings = Settings.load()
    configure_logging(secret_values=settings.secret_values())
    setup_telemetry(
        service_name="jobpilot-worker", otlp_endpoint=settings.otel_exporter_otlp_endpoint
    )

    bot = Bot(token=settings.telegram_api_token.get_secret_value())
    services = Services(settings, bot)

    scheduler = AsyncIOScheduler(timezone=settings.tz_scheduler)
    scheduler.add_job(
        services.run_digest_as_job,
        CronTrigger.from_crontab(settings.digest_cron, timezone=settings.tz_scheduler),
        id="daily_digest",
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        services.build_invites_as_job,
        CronTrigger.from_crontab(settings.invites_cron, timezone=settings.tz_scheduler),
        id="weekly_invites",
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        services.publish_as_job,
        IntervalTrigger(hours=settings.publish_interval_hours),
        id="publish_resume",
        coalesce=True,
        misfire_grace_time=600,
    )
    scheduler.start()
    log.info(
        "worker_started",
        tz=settings.tz_scheduler,
        dry_run=settings.dry_run,
        digest_cron=settings.digest_cron,
        publish_interval_hours=settings.publish_interval_hours,
        invites_cron=settings.invites_cron,
    )

    stop = asyncio.Event()
    await stop.wait()


if __name__ == "__main__":
    asyncio.run(main())
