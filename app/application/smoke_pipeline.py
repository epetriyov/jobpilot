"""RunSmokePipeline — DRY_RUN-смоук этапа 0 ([F-I2], [X-I1]).

Проходит все шаги дневного пайплайна на фикстурах (сбор → дедуп → формирование
дайджеста), но при DRY_RUN не делает внешних записей (publish) и метит дайджест «ТЕСТ».
Полноценный дайджест с реальными источниками и скорингом — этап 1.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from opentelemetry import trace

from app.domain.sourcing import DedupIndex, Vacancy, collect_from_sources
from app.obs.metrics import (
    digest_sent_total,
    scraper_failures_total,
    vacancies_discovered_total,
)
from app.ports.notifier import NotifierPort, PublisherPort

log = structlog.get_logger("application.smoke_pipeline")
tracer = trace.get_tracer("jobpilot.application")

DRY_RUN_MARK = "🧪 ТЕСТ (DRY_RUN)"


@dataclass
class SmokeResult:
    dry_run: bool
    digest_items: int
    partial: bool


class RunSmokePipeline:
    def __init__(
        self,
        *,
        notifier: NotifierPort,
        publisher: PublisherPort,
        dry_run: bool,
        sources: dict[str, Callable[[], list[Vacancy]]],
    ) -> None:
        self._notifier = notifier
        self._publisher = publisher
        self._dry_run = dry_run
        self._sources = sources

    async def run(self) -> SmokeResult:
        with tracer.start_as_current_span("smoke.collect") as span:
            collected = collect_from_sources(self._sources)
            span.set_attribute("vacancies.in", len(collected.vacancies))
            for failure in collected.failures:
                scraper_failures_total.add(1, {"site": failure.source})
                log.warning("source_fetch_failed", source=failure.source, error=failure.error)

        with tracer.start_as_current_span("smoke.dedup"):
            index = DedupIndex()
            now = datetime.now(UTC)
            fresh = []
            for vacancy in collected.vacancies:
                if index.ingest(vacancy, now=now) is not None:
                    fresh.append(vacancy)
                    vacancies_discovered_total.add(1, {"source": vacancy.source_ref.source})

        with tracer.start_as_current_span("smoke.publish"):
            if self._dry_run:
                log.info("publish_skipped", dry_run=True)
            else:
                await self._publisher.publish()

        with tracer.start_as_current_span("smoke.notify"):
            digest = self._render_digest(fresh)
            await self._notifier.send_digest(digest)
            digest_sent_total.add(1, {"dry_run": str(self._dry_run).lower()})

        return SmokeResult(
            dry_run=self._dry_run, digest_items=len(fresh), partial=collected.partial
        )

    def _render_digest(self, vacancies: list[Vacancy]) -> str:
        header = DRY_RUN_MARK if self._dry_run else "📋 Дайджест"
        lines = [header, f"Вакансий: {len(vacancies)}"]
        lines += [f"• {v.title} — {v.company} ({v.url})" for v in vacancies]
        return "\n".join(lines)
