"""[T112] LabelVacancy: 👍/👎 → upsert labeled_vacancy из снапшота seen,
повторное нажатие обновляет вердикт без дубликата, строка уходит в eval-датасет.
"""

from app.application.label_vacancy import LabelVacancy
from app.domain.relevance import LabeledVacancy, VacancySnapshot
from app.domain.shared import Source, SourceRef

REF = SourceRef(source=Source.HH, external_id="42")

SNAPSHOT = VacancySnapshot(
    source_ref=REF,
    title="Engineering Manager",
    company="Acme",
    url="https://hh.ru/vacancy/42",
    description_text="Команда 10 человек",
)


class SeenFake:
    def __init__(self, snapshots: dict[str, VacancySnapshot]) -> None:
        self._snapshots = snapshots

    async def snapshot(self, ref: SourceRef) -> VacancySnapshot | None:
        return self._snapshots.get(ref.as_key())


class LabelsFake:
    def __init__(self) -> None:
        self.by_ref: dict[str, LabeledVacancy] = {}
        self.upserts = 0

    async def upsert(self, labeled: LabeledVacancy) -> None:
        self.upserts += 1
        self.by_ref[labeled.source_ref.as_key()] = labeled

    async def counts(self) -> tuple[int, int]:
        relevant = sum(1 for v in self.by_ref.values() if v.verdict == "relevant")
        return relevant, len(self.by_ref) - relevant


class DatasetFake:
    def __init__(self) -> None:
        self.lines: list[dict] = []  # type: ignore[type-arg]

    def append(self, example: dict) -> None:  # type: ignore[type-arg]
        self.lines.append(example)


def make_use_case(labels: LabelsFake, dataset: DatasetFake) -> LabelVacancy:
    return LabelVacancy(
        seen_repo=SeenFake({REF.as_key(): SNAPSHOT}), label_repo=labels, dataset=dataset
    )


async def test_label_saves_snapshot_with_verdict() -> None:
    labels, dataset = LabelsFake(), DatasetFake()

    labeled = await make_use_case(labels, dataset).label("hh:42", "relevant")

    assert labeled is not None and labeled.verdict == "relevant"
    assert labels.by_ref["hh:42"].title == "Engineering Manager"
    assert dataset.lines[0]["id"] == "hh:42"
    assert dataset.lines[0]["expected"] == {"verdict": "relevant"}


async def test_repeat_updates_verdict_no_duplicate() -> None:
    labels, dataset = LabelsFake(), DatasetFake()
    use_case = make_use_case(labels, dataset)

    await use_case.label("hh:42", "relevant")
    await use_case.label("hh:42", "irrelevant")

    assert len(labels.by_ref) == 1  # один снапшот, вердикт обновлён
    assert labels.by_ref["hh:42"].verdict == "irrelevant"
    assert len(dataset.lines) == 2  # датасет append-only: обе строки (последняя побеждает)


async def test_unknown_ref_returns_none_and_writes_nothing() -> None:
    labels, dataset = LabelsFake(), DatasetFake()

    labeled = await make_use_case(labels, dataset).label("hh:404", "relevant")

    assert labeled is None
    assert labels.by_ref == {} and dataset.lines == []


async def test_progress_counts() -> None:
    labels, dataset = LabelsFake(), DatasetFake()
    use_case = make_use_case(labels, dataset)
    await use_case.label("hh:42", "relevant")

    relevant, irrelevant = await use_case.progress()

    assert (relevant, irrelevant) == (1, 0)
