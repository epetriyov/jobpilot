"""Use case LabelVacancy: 👍/👎 владельца → Label + строка eval-датасета.

Снапшот берётся из реестра seen — разметка работает, даже если вакансия
уже удалена из источника (edge case спеки этапа 1). Повторная разметка
обновляет вердикт (upsert), датасет остаётся append-only (последний
вердикт по id побеждает при прогоне eval).
"""

from __future__ import annotations

import structlog

from app.domain.relevance import LabeledVacancy, Verdict
from app.domain.shared import Source, SourceRef
from app.ports.embeddings import EmbeddingPort
from app.ports.repositories import (
    DatasetAppenderPort,
    LabelRepositoryPort,
    ScoringRepositoryPort,
)

log = structlog.get_logger("application.label_vacancy")


class LabelVacancy:
    def __init__(
        self,
        *,
        seen_repo: ScoringRepositoryPort,
        label_repo: LabelRepositoryPort,
        dataset: DatasetAppenderPort,
        embedder: EmbeddingPort | None = None,
    ) -> None:
        self._seen = seen_repo
        self._labels = label_repo
        self._dataset = dataset
        # этап 6D: при наличии — считаем эмбеддинг сразу при разметке (иначе backfill-джоб)
        self._embedder = embedder

    async def label(self, ref_key: str, verdict: Verdict) -> LabeledVacancy | None:
        snapshot = await self._seen.snapshot(_ref_from_key(ref_key))
        if snapshot is None:
            log.warning("label_snapshot_missing", source_ref=ref_key)
            return None

        labeled = LabeledVacancy(**snapshot.model_dump(), verdict=verdict)
        embedding = None
        if self._embedder is not None:
            from app.application.fewshot import vacancy_text

            embedding = await self._embedder.embed(vacancy_text(labeled))
        await self._labels.upsert(labeled, embedding)
        self._dataset.append(
            {
                "id": ref_key,
                "input": {
                    "title": snapshot.title,
                    "company": snapshot.company,
                    "vacancy_text": snapshot.description_text,
                },
                "expected": {"verdict": verdict},
                "meta": {"source": "review"},
            }
        )
        log.info("label_added", source_ref=ref_key, verdict=verdict)
        return labeled

    async def progress(self) -> tuple[int, int]:
        """(relevant, irrelevant) — для /train."""
        return await self._labels.counts()


def _ref_from_key(key: str) -> SourceRef:
    parts = key.split(":")
    source = Source(parts[0])
    if source is Source.SITE:
        return SourceRef(source=source, site_name=parts[1], external_id=":".join(parts[2:]))
    return SourceRef(source=source, external_id=":".join(parts[1:]))
