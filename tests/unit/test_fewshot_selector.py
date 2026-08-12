"""[T6D-4] Few-shot селекторы: RecentSelector, SemanticSelector + фолбэк.

Semantic подбирает ближайшие по эмбеддингу текущей вакансии; при < min_embedded
размеченных с эмбеддингами — фолбэк на recent ([R-U2]-совместимо), без падения.
"""

from __future__ import annotations

from app.application.fewshot import RecentSelector, SemanticSelector, vacancy_text
from app.domain.relevance import LabeledVacancy, VacancySnapshot
from app.domain.shared import Source, SourceRef
from app.ports.llm import LlmCallRecord


def snap(i: int, text: str = "Python highload найм лидов") -> VacancySnapshot:
    return VacancySnapshot(
        source_ref=SourceRef(source=Source.HH, external_id=str(i)),
        title=f"Engineering Manager {i}",
        company="Acme",
        url=f"https://hh.ru/vacancy/{i}",
        description_text=text,
    )


def label(i: int, verdict: str = "relevant", text: str = "Python highload") -> LabeledVacancy:
    return LabeledVacancy(**snap(i, text).model_dump(), verdict=verdict)  # type: ignore[arg-type]


class Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


class LabelRepoFake:
    def __init__(
        self,
        *,
        recent: list[LabeledVacancy] | None = None,
        nearest: list[LabeledVacancy] | None = None,
        embedded: int = 0,
    ) -> None:
        self._recent = recent or []
        self._nearest = nearest or []
        self._embedded = embedded
        self.nearest_calls = 0

    async def recent(self, limit: int = 10) -> list[LabeledVacancy]:
        return self._recent[:limit]

    async def nearest(self, embedding: list[float], k: int = 10) -> list[LabeledVacancy]:
        self.nearest_calls += 1
        return self._nearest[:k]

    async def embedded_count(self) -> int:
        return self._embedded


async def test_recent_selector_returns_last_n_pairs() -> None:
    repo = LabelRepoFake(recent=[label(i) for i in range(12)])
    selector = RecentSelector(repo, limit=10, text_limit=800)  # type: ignore[arg-type]
    pairs = await selector.select_for(snap(100))
    assert len(pairs) == 10
    assert all(isinstance(u, str) and isinstance(a, str) for u, a in pairs)


async def test_recent_selector_caches_across_vacancies() -> None:
    """RecentSelector строит few-shot один раз (одинаков для всех вакансий прогона)."""

    class Counting(LabelRepoFake):
        def __init__(self) -> None:
            super().__init__(recent=[label(1)])
            self.recent_calls = 0

        async def recent(self, limit: int = 10) -> list[LabeledVacancy]:
            self.recent_calls += 1
            return self._recent[:limit]

    repo = Counting()
    selector = RecentSelector(repo, limit=10, text_limit=800)  # type: ignore[arg-type]
    await selector.select_for(snap(1))
    await selector.select_for(snap(2))
    assert repo.recent_calls == 1


async def test_semantic_selector_uses_nearest_when_enough_embedded() -> None:
    from app.adapters.embeddings.fake import FakeEmbedder

    repo = LabelRepoFake(
        recent=[label(1)],
        nearest=[label(i, text=f"близкий {i}") for i in range(5)],
        embedded=50,
    )
    embedder = FakeEmbedder(recorder=Recorder())
    selector = SemanticSelector(
        repo,  # type: ignore[arg-type]
        embedder=embedder,
        limit=5,
        text_limit=800,
        min_embedded=20,
    )
    pairs = await selector.select_for(snap(100))
    assert repo.nearest_calls == 1
    assert len(pairs) == 5


async def test_semantic_selector_falls_back_to_recent_below_threshold() -> None:
    from app.adapters.embeddings.fake import FakeEmbedder

    repo = LabelRepoFake(recent=[label(i) for i in range(3)], nearest=[], embedded=5)
    embedder = FakeEmbedder(recorder=Recorder())
    selector = SemanticSelector(
        repo,  # type: ignore[arg-type]
        embedder=embedder,
        limit=10,
        text_limit=800,
        min_embedded=20,
    )
    pairs = await selector.select_for(snap(100))
    assert repo.nearest_calls == 0  # фолбэк: nearest не звался
    assert len(pairs) == 3  # взяты recent


def test_vacancy_text_combines_title_company_description() -> None:
    text = vacancy_text(snap(1, "описание команды"))
    assert "Engineering Manager 1" in text
    assert "описание команды" in text
