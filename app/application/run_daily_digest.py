"""Use case RunDailyDigest — продукт этапа 1 (spec 001, US1).

Сбор из источников (S4 — изоляция падений) → реестр seen со снапшотом (S1) →
кросс-дедуп (S2: дубликат исключается из дайджеста) → скоринг новых (R1–R3) →
отбор (R4: порог/топ-N) → карточки в чат → пометка digest_sent.
DRY_RUN помечает дайджест «ТЕСТ» ([F-I2]); пометка sent ставится и в DRY_RUN —
иначе те же карточки приходили бы ежедневно.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from opentelemetry import trace

from app.application.score_vacancy import ScoreVacancy
from app.domain.relevance import select_for_digest
from app.domain.shared import SourceRef
from app.domain.sourcing import Vacancy
from app.obs.metrics import (
    digest_sent_total,
    scraper_failures_total,
    vacancies_discovered_total,
)
from app.ports.notifier import DigestCard, NotifierPort
from app.ports.repositories import DigestRepositoryPort, ScoredCandidate
from app.ports.sources import VacancySourcePort

log = structlog.get_logger("application.run_daily_digest")
tracer = trace.get_tracer("jobpilot.application")

DRY_RUN_MARK = "🧪 ТЕСТ (DRY_RUN)"


@dataclass
class DigestResult:
    dry_run: bool
    discovered: int
    cards_sent: int
    partial: bool


class RunDailyDigest:
    def __init__(
        self,
        *,
        sources: Sequence[VacancySourcePort],
        seen_repo: DigestRepositoryPort,
        scorer: ScoreVacancy,
        notifier: NotifierPort,
        dry_run: bool,
        threshold: int,
        max_items: int,
    ) -> None:
        self._sources = sources
        self._seen = seen_repo
        self._scorer = scorer
        self._notifier = notifier
        self._dry_run = dry_run
        self._threshold = threshold
        self._max_items = max_items

    async def run(self) -> DigestResult:
        collected, failed = await self._collect()
        discovered = await self._register(collected)

        with tracer.start_as_current_span("digest.scoring"):
            await self._scorer.score_pending()

        with tracer.start_as_current_span("digest.select") as span:
            cards = await self._select_cards()
            span.set_attribute("digest.cards", len(cards))

        # health-сигнал: источники есть, но сырьё пустое → сбой доступа
        # (мёртвый токен, сменившийся формат письма, блокировка), а НЕ «всё видели»
        sources_empty = bool(self._sources) and not collected
        if sources_empty:
            log.warning("digest_sources_empty", sources=len(self._sources), failed=failed)

        with tracer.start_as_current_span("digest.notify"):
            await self._send(cards, sources_empty=sources_empty)

        partial = failed > 0 and len(collected) > 0
        log.info(
            "digest_done",
            discovered=discovered,
            cards=len(cards),
            partial=partial,
            dry_run=self._dry_run,
        )
        return DigestResult(
            dry_run=self._dry_run,
            discovered=discovered,
            cards_sent=len(cards),
            partial=partial,
        )

    async def _collect(self) -> tuple[list[Vacancy], int]:
        collected: list[Vacancy] = []
        failed = 0
        with tracer.start_as_current_span("digest.collect") as span:
            for source in self._sources:
                try:
                    items = await source.fetch()
                    collected.extend(items)
                except Exception as exc:
                    failed += 1
                    scraper_failures_total.add(1, {"site": source.name})
                    log.warning("source_fetch_failed", source=source.name, error=str(exc))
            span.set_attribute("vacancies.in", len(collected))
        return collected, failed

    async def _register(self, collected: list[Vacancy]) -> int:
        """S1/S2: реестр seen со снапшотом; кросс-дубликаты исключаются из дайджеста."""
        discovered = 0
        now = datetime.now(UTC)
        with tracer.start_as_current_span("digest.dedup"):
            for vacancy in collected:
                ref = vacancy.source_ref
                if await self._seen.is_seen(ref):
                    continue
                duplicate_of = await self._seen.find_duplicate(vacancy.normalized_key())
                await self._seen.mark_seen(vacancy)
                if duplicate_of is not None and duplicate_of != ref.as_key():
                    # S2: остаётся в реестре, но не попадает в скоринг и дайджест
                    await self._seen.mark_digest_sent([ref], now)
                    log.info(
                        "cross_source_duplicate",
                        source_ref=ref.as_key(),
                        duplicate_of=duplicate_of,
                    )
                    continue
                discovered += 1
                vacancies_discovered_total.add(1, {"source": ref.source})
        return discovered

    async def _select_cards(self) -> list[DigestCard]:
        candidates = await self._seen.unsent_scored()
        by_key: dict[str, ScoredCandidate] = {c.snapshot.source_ref.as_key(): c for c in candidates}
        pairs = [(key, c.score) for key, c in by_key.items()]
        selected = select_for_digest(pairs, threshold=self._threshold, max_items=self._max_items)
        return [
            DigestCard(
                ref_key=key,
                title=by_key[key].snapshot.title,
                company=by_key[key].snapshot.company,
                url=by_key[key].snapshot.url,
                salary_text=by_key[key].salary_text,
                score=score.value,
                reason=score.reason,
            )
            for key, score in selected
        ]

    async def _send(self, cards: list[DigestCard], *, sources_empty: bool = False) -> None:
        header = DRY_RUN_MARK if self._dry_run else "📋 Дайджест"
        if not cards:
            if sources_empty:
                # видимый владельцу сигнал сбоя — иначе «0 вакансий» тонет как норма
                await self._notifier.send_digest(
                    f"{header}\n⚠️ Источники вернули 0 вакансий за период. "
                    "Похоже на сбой доступа (токен/формат письма/блокировка), "
                    "а не отсутствие новых — проверь логи и подписку."
                )
            else:
                await self._notifier.send_digest(f"{header}\nНовых релевантных вакансий нет.")
            return
        await self._notifier.send_digest(f"{header}\nРелевантных вакансий: {len(cards)}")
        sent_refs: list[SourceRef] = []
        for card in cards:
            await self._notifier.send_card(card)
            sent_refs.append(_ref_from_key(card.ref_key))
        await self._seen.mark_digest_sent(sent_refs, datetime.now(UTC))
        digest_sent_total.add(1, {"dry_run": str(self._dry_run).lower()})


def _ref_from_key(key: str) -> SourceRef:
    from app.domain.shared import Source

    parts = key.split(":")
    source = Source(parts[0])
    if source is Source.SITE:
        return SourceRef(source=source, site_name=parts[1], external_id=":".join(parts[2:]))
    return SourceRef(source=source, external_id=":".join(parts[1:]))
