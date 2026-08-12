"""Use case BackfillEmbeddings: идемпотентное наполнение `labeled_vacancy.embedding`.

Считает эмбеддинги только для размеченных без вектора (missing_embeddings) — повторный
запуск после полного наполнения ничего не делает. LLM-вызовы вне миграции (research §3);
каждый эмбеддинг = учтённый `llm_call` (O1) через EmbeddingPort.
"""

from __future__ import annotations

import structlog

from app.application.fewshot import vacancy_text
from app.ports.embeddings import EmbeddingPort
from app.ports.repositories import LabelRepositoryPort

log = structlog.get_logger("application.backfill_embeddings")


class BackfillEmbeddings:
    def __init__(self, *, label_repo: LabelRepositoryPort, embedder: EmbeddingPort) -> None:
        self._labels = label_repo
        self._embedder = embedder

    async def run(self, batch_limit: int = 200) -> int:
        """Наполнить эмбеддинги пачкой ≤ batch_limit; вернуть число обработанных."""
        missing = await self._labels.missing_embeddings(batch_limit)
        log.info("backfill_start", missing=len(missing))
        done = 0
        for labeled in missing:
            embedding = await self._embedder.embed(vacancy_text(labeled))
            await self._labels.set_embedding(labeled.source_ref, embedding)
            done += 1
        log.info("backfill_finish", embedded=done)
        return done
