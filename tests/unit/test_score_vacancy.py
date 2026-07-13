"""[R-U1] [R-U5] Use case ScoreVacancy: R1 (не скорить повторно), R2 (skip не роняет),
R3 (few-shot из размеченных). На фейковом LlmPort и in-memory репозиториях.
"""

from app.adapters.llm.fake import FakeLlm
from app.application.score_vacancy import ScoreVacancy
from app.domain.relevance import LabeledVacancy, Score, VacancySnapshot
from app.domain.shared import PromptVersion, Source, SourceRef
from app.ports.llm import LlmCallRecord

PV = PromptVersion(purpose="scoring", version=1)


def snap(i: int) -> VacancySnapshot:
    return VacancySnapshot(
        source_ref=SourceRef(source=Source.HH, external_id=str(i)),
        title=f"Engineering Manager {i}",
        company="Acme",
        url=f"https://hh.ru/vacancy/{i}",
        description_text=f"Команда {i} человек, стек Python",
    )


def label(i: int, verdict: str) -> LabeledVacancy:
    return LabeledVacancy(**snap(i).model_dump(), verdict=verdict)  # type: ignore[arg-type]


class SeenRepoFake:
    def __init__(self, pending: list[VacancySnapshot]) -> None:
        self.pending = pending
        self.saved: dict[str, Score] = {}

    async def unscored(self, prompt_version: str, limit: int = 100) -> list[VacancySnapshot]:
        return self.pending[:limit]

    async def save_score(self, ref: SourceRef, score: Score) -> None:
        self.saved[ref.as_key()] = score


class LabelRepoFake:
    def __init__(self, labels: list[LabeledVacancy] | None = None) -> None:
        self.labels = labels or []

    async def recent(self, limit: int = 10) -> list[LabeledVacancy]:
        return self.labels[:limit]


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


VALID = '{"score": 77, "reason": "хороший матч"}'
INVALID = '{"score": 150, "reason": "мимо схемы"}'


def make_use_case(
    llm: FakeLlm, seen: SeenRepoFake, labels: LabelRepoFake | None = None
) -> ScoreVacancy:
    return ScoreVacancy(
        llm=llm,
        seen_repo=seen,
        label_repo=labels or LabelRepoFake(),
        system_prompt="Ты оцениваешь вакансии для EM.",
        prompt_version=PV,
        model_name="google/gemini-2.5-flash-lite",
    )


async def test_scores_pending_and_saves() -> None:
    seen = SeenRepoFake([snap(1), snap(2)])
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID, VALID])

    scored = await make_use_case(llm, seen).score_pending()

    assert scored == 2
    assert set(seen.saved) == {"hh:1", "hh:2"}
    saved = seen.saved["hh:1"]
    assert saved.value == 77
    assert saved.prompt_version == "scoring_v1"
    assert saved.model == "google/gemini-2.5-flash-lite"


async def test_r1_only_unscored_are_sent_to_llm() -> None:
    """[R-U5] Скоренные текущей версией не запрашиваются повторно: use case
    работает только с выборкой unscored(prompt_version) и не трогает остальное."""
    seen = SeenRepoFake([snap(3)])  # unscored вернул только одну
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID, VALID, VALID])

    await make_use_case(llm, seen).score_pending()

    assert llm.attempts == 1  # ровно один вызов LLM
    assert set(seen.saved) == {"hh:3"}


async def test_r2_invalid_skips_vacancy_pipeline_alive() -> None:
    """[R-U1] Невалидно дважды → skip вакансии; остальные скорятся."""
    seen = SeenRepoFake([snap(1), snap(2)])
    llm = FakeLlm(recorder=RecorderSpy(), responses=[INVALID, "не json", VALID])

    scored = await make_use_case(llm, seen).score_pending()

    assert scored == 1
    assert set(seen.saved) == {"hh:2"}  # первая пропущена после 1 ретрая
    assert llm.attempts == 3


async def test_r3_few_shot_from_labels() -> None:
    """[R-U2]-механика в use case: до 10 последних размеченных попадают в промпт."""
    labels = LabelRepoFake([label(i, "relevant") for i in range(12)])
    seen = SeenRepoFake([snap(100)])
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID])

    await make_use_case(llm, seen, labels).score_pending()

    # 1 system + 10 пар few-shot (user+assistant) + 1 data-сообщение
    assert len(llm.sent_messages) == 1 + 10 * 2 + 1


async def test_llm_call_recorded_for_each_scoring() -> None:
    """O1: каждый скоринг оставляет llm_call (через адаптер)."""
    recorder = RecorderSpy()
    seen = SeenRepoFake([snap(1), snap(2)])
    llm = FakeLlm(recorder=recorder, responses=[VALID, VALID])

    await make_use_case(llm, seen).score_pending()

    assert len(recorder.records) == 2
    assert all(r.purpose == "scoring" for r in recorder.records)
