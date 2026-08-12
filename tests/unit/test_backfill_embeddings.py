"""[T6D-3] Идемпотентный backfill эмбеддингов размеченных вакансий.

Считает эмбеддинги только для строк без вектора; повторный прогон после полного
наполнения ничего не делает (missing → пусто). Каждый эмбеддинг → llm_call (O1).
"""

from __future__ import annotations

from app.adapters.embeddings.fake import FakeEmbedder
from app.application.backfill_embeddings import BackfillEmbeddings
from app.domain.relevance import LabeledVacancy, VacancySnapshot
from app.domain.shared import Source, SourceRef
from app.ports.llm import LlmCallRecord


def labeled(i: int) -> LabeledVacancy:
    snap = VacancySnapshot(
        source_ref=SourceRef(source=Source.HH, external_id=str(i)),
        title=f"EM {i}",
        company="Acme",
        url=f"https://hh.ru/vacancy/{i}",
        description_text=f"описание {i} Python highload",
    )
    return LabeledVacancy(**snap.model_dump(), verdict="relevant")  # type: ignore[arg-type]


class Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


class LabelRepoFake:
    def __init__(self, count: int) -> None:
        self._rows = {str(i): labeled(i) for i in range(count)}
        self._embeddings: dict[str, list[float]] = {}

    async def missing_embeddings(self, limit: int = 200) -> list[LabeledVacancy]:
        missing = [row for key, row in self._rows.items() if key not in self._embeddings]
        return missing[:limit]

    async def set_embedding(self, source_ref: SourceRef, embedding: list[float]) -> None:
        self._embeddings[source_ref.external_id] = embedding

    async def embedded_count(self) -> int:
        return len(self._embeddings)


async def test_backfill_embeds_all_missing() -> None:
    repo = LabelRepoFake(count=5)
    embedder = FakeEmbedder(recorder=Recorder())
    use_case = BackfillEmbeddings(label_repo=repo, embedder=embedder)  # type: ignore[arg-type]

    done = await use_case.run()

    assert done == 5
    assert await repo.embedded_count() == 5


async def test_backfill_is_idempotent() -> None:
    repo = LabelRepoFake(count=3)
    recorder = Recorder()
    embedder = FakeEmbedder(recorder=recorder)
    use_case = BackfillEmbeddings(label_repo=repo, embedder=embedder)  # type: ignore[arg-type]

    first = await use_case.run()
    second = await use_case.run()

    assert first == 3
    assert second == 0  # всё уже наполнено — второй прогон ничего не делает
    assert len(recorder.records) == 3  # llm_call только за первый прогон


async def test_backfill_respects_batch_limit() -> None:
    repo = LabelRepoFake(count=10)
    embedder = FakeEmbedder(recorder=Recorder())
    use_case = BackfillEmbeddings(label_repo=repo, embedder=embedder)  # type: ignore[arg-type]

    done = await use_case.run(batch_limit=4)

    assert done == 4
    assert await repo.embedded_count() == 4
