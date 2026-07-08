"""`make smoke`: тестовый DRY_RUN-прогон пайплайна на фикстурах (quickstart §4).

Печатает дайджест в stdout и логирует телеметрию. Реальная отправка в Telegram
происходит, только если DRY_RUN=false и заданы креды — на этапе 0 по умолчанию DRY_RUN.
"""

from __future__ import annotations

import asyncio

import structlog

from app.application.smoke_pipeline import RunSmokePipeline
from app.config import Settings
from app.obs.logging import configure_logging
from app.obs.telemetry import setup_telemetry
from app.worker.fixtures import sample_hh

log = structlog.get_logger("worker.smoke")


class StdoutNotifier:
    async def send_digest(self, text: str) -> None:
        print(text)

    async def send_message(self, text: str) -> None:
        print(text)


class NullPublisher:
    async def publish(self) -> None:
        return None


async def main() -> None:
    settings = Settings.load()
    configure_logging(secret_values=settings.secret_values())
    setup_telemetry(
        service_name="jobpilot-smoke", otlp_endpoint=settings.otel_exporter_otlp_endpoint
    )

    pipeline = RunSmokePipeline(
        notifier=StdoutNotifier(),
        publisher=NullPublisher(),
        dry_run=settings.dry_run,
        sources={"hh": sample_hh},
    )
    result = await pipeline.run()
    log.info(
        "smoke_done",
        dry_run=result.dry_run,
        digest_items=result.digest_items,
        partial=result.partial,
    )


if __name__ == "__main__":
    asyncio.run(main())
