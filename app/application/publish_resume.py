"""Use case PublishResume: поднятие резюме (спека 001 US3, [S-C3], [F-I2])."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog

from app.obs.metrics import publish_skipped_total
from app.ports.notifier import PublisherPort

log = structlog.get_logger("application.publish_resume")


@dataclass
class PublishResult:
    status: Literal["published", "skipped_limit", "dry_run", "disabled"]


class PublishResume:
    def __init__(self, *, publisher: PublisherPort, dry_run: bool) -> None:
        self._publisher = publisher
        self._dry_run = dry_run

    async def run(self) -> PublishResult:
        if self._dry_run:
            log.info("publish_skipped", dry_run=True)
            return PublishResult(status="dry_run")

        outcome = await self._publisher.publish()
        if outcome == "skipped_limit":
            # [S-C3]: лимит — штатно; info-лог, метрика, БЕЗ ретрая до следующего слота
            publish_skipped_total.add(1)
            log.info("publish_skipped", reason="limit")
            return PublishResult(status="skipped_limit")

        if outcome == "disabled":
            # рабочего канала поднятия нет — честно, без ложного resume_published
            log.info("publish_disabled", reason="no_publisher")
            return PublishResult(status="disabled")

        log.info("resume_published")
        return PublishResult(status="published")
