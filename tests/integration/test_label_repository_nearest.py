"""[T6D-3] LabelRepository поверх pgvector: nearest / backfill-методы на реальной БД.

Проверяет: upsert с эмбеддингом; nearest возвращает семантически ближайшую метку
первой (cosine `<=>`); missing_embeddings/set_embedding/embedded_count для backfill.
"""

from __future__ import annotations

import pytest

from app.adapters.embeddings.fake import FakeEmbedder
from app.adapters.persistence.repositories import LabelRepository
from app.application.fewshot import vacancy_text
from app.domain.relevance import LabeledVacancy, VacancySnapshot
from app.domain.shared import Source, SourceRef
from app.ports.llm import LlmCallRecord

pytestmark = pytest.mark.integration


class Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


def labeled(ext: str, text: str, verdict: str = "relevant") -> LabeledVacancy:
    snap = VacancySnapshot(
        source_ref=SourceRef(source=Source.HH, external_id=ext),
        title=f"Role {ext}",
        company="Acme",
        url=f"https://hh.ru/vacancy/{ext}",
        description_text=text,
    )
    return LabeledVacancy(**snap.model_dump(), verdict=verdict)  # type: ignore[arg-type]


async def test_nearest_returns_semantically_closest(db_session) -> None:
    repo = LabelRepository(db_session)
    embedder = FakeEmbedder(recorder=Recorder())

    rows = {
        "1": "Python highload backend найм лидов",
        "2": "продажи недвижимости холодные звонки",
        "3": "мобильная разработка Swift iOS дизайн",
    }
    for ext, text in rows.items():
        emb = await embedder.embed(text)
        await repo.upsert(labeled(ext, text), emb)
    await db_session.flush()

    query = await embedder.embed("backend Python найм highload инженеров")
    nearest = await repo.nearest(query, k=1)

    assert len(nearest) == 1
    assert nearest[0].source_ref.external_id == "1"


async def test_backfill_methods_roundtrip(db_session) -> None:
    repo = LabelRepository(db_session)
    embedder = FakeEmbedder(recorder=Recorder())

    await repo.upsert(labeled("10", "текст без эмбеддинга"))
    await repo.upsert(labeled("11", "ещё один без эмбеддинга"))
    await db_session.flush()

    assert await repo.embedded_count() == 0
    missing = await repo.missing_embeddings()
    assert {m.source_ref.external_id for m in missing} == {"10", "11"}

    for m in missing:
        await repo.set_embedding(m.source_ref, await embedder.embed(vacancy_text(m)))
    await db_session.flush()

    assert await repo.embedded_count() == 2
    assert await repo.missing_embeddings() == []


async def test_upsert_updates_embedding_on_relabel(db_session) -> None:
    repo = LabelRepository(db_session)
    embedder = FakeEmbedder(recorder=Recorder())

    first = await embedder.embed("первый текст")
    await repo.upsert(labeled("20", "первый текст", "relevant"), first)
    await db_session.flush()
    assert await repo.embedded_count() == 1

    second = await embedder.embed("совсем другой текст разметки")
    await repo.upsert(labeled("20", "первый текст", "irrelevant"), second)
    await db_session.flush()

    # тот же source_ref: одна строка, обновлённый вердикт и эмбеддинг
    assert await repo.embedded_count() == 1
    relevant, irrelevant = await repo.counts()
    assert (relevant, irrelevant) == (0, 1)
