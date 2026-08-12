"""Few-shot селекторы как стратегия (этап 6D, FR-006).

Две стратегии за единым портом `FewShotSelectorPort`, инъектируемым в ScoreVacancy:
- `RecentSelector` — «последние N» размеченных (R3, дефолт; строит пары один раз);
- `SemanticSelector` — ближайшие по эмбеддингу текущей вакансии (pgvector), с
  фолбэком на recent, пока размеченных с эмбеддингами < min_embedded ([R-U2]-совместимо).

Домен скоринга не ветвится: выбор стратегии — в композиции по конфигу FEWSHOT_SELECTOR.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.relevance import VacancySnapshot, build_few_shot
from app.ports.embeddings import EmbeddingPort
from app.ports.repositories import LabelRepositoryPort


def vacancy_text(snapshot: VacancySnapshot) -> str:
    """Единый текст вакансии для скоринга и эмбеддинга (title — company — описание)."""
    return f"{snapshot.title} — {snapshot.company}\n{snapshot.description_text}"


class FewShotSelectorPort(Protocol):
    async def select_for(self, snapshot: VacancySnapshot) -> list[tuple[str, str]]:
        """Пары (user, assistant) few-shot для скоринга данной вакансии."""
        ...


class RecentSelector:
    """«Последние N» размеченных (R3). Кэширует пары — один набор на прогон."""

    def __init__(self, label_repo: LabelRepositoryPort, *, limit: int, text_limit: int) -> None:
        self._labels = label_repo
        self._limit = limit
        self._text_limit = text_limit
        self._cache: list[tuple[str, str]] | None = None

    async def select_for(self, snapshot: VacancySnapshot) -> list[tuple[str, str]]:
        if self._cache is None:
            labels = await self._labels.recent(self._limit)
            self._cache = build_few_shot(labels, limit=self._limit, text_limit=self._text_limit)
        return self._cache


class SemanticSelector:
    """Ближайшие по эмбеддингу текущей вакансии; фолбэк на recent под порогом."""

    def __init__(
        self,
        label_repo: LabelRepositoryPort,
        *,
        embedder: EmbeddingPort,
        limit: int,
        text_limit: int,
        min_embedded: int,
    ) -> None:
        self._labels = label_repo
        self._embedder = embedder
        self._limit = limit
        self._text_limit = text_limit
        self._min_embedded = min_embedded
        self._fallback = RecentSelector(label_repo, limit=limit, text_limit=text_limit)
        self._enough: bool | None = None

    async def select_for(self, snapshot: VacancySnapshot) -> list[tuple[str, str]]:
        if self._enough is None:
            self._enough = await self._labels.embedded_count() >= self._min_embedded
        if not self._enough:
            return await self._fallback.select_for(snapshot)
        embedding = await self._embedder.embed(vacancy_text(snapshot))
        labels = await self._labels.nearest(embedding, self._limit)
        return build_few_shot(labels, limit=self._limit, text_limit=self._text_limit)
