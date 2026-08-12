"""EmbeddingPort — единственная точка получения эмбеддингов (constitution III, FR-009).

Прямые вызовы embedding-SDK вне app/adapters/embeddings/ запрещены (как и LlmPort).
Каждый эмбеддинг = учтённый `llm_call` (purpose=`embedding`, O1). Размерность 768
зафиксирована схемой `labeled_vacancy.embedding vector(768)` (data-model §3).
"""

from __future__ import annotations

from typing import Protocol

from app.domain.shared import PromptVersion

# размерность вектора — контракт со схемой БД (labeled_vacancy.embedding vector(768))
EMBEDDING_DIM = 768

# псевдо-версия промпта для учёта llm_call (у эмбеддингов нет текстового промпта,
# но O1 требует непустой prompt_version; смена модели = новая версия при интеграции)
EMBEDDING_PROMPT_VERSION = PromptVersion(purpose="embedding", version=1)


class EmbeddingPort(Protocol):
    """Отдаёт нормализованный вектor длины EMBEDDING_DIM для текста."""

    async def embed(self, text: str) -> list[float]:
        """Вектор эмбеддинга (len == EMBEDDING_DIM). Каждый вызов → llm_call (O1)."""
        ...
