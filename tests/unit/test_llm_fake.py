"""[F-U3] Любой вызов через LlmPort → запись llm_call (инвариант O1) — на фейке.
[R-U1] Невалидный выход → ровно 1 retry → graceful skip, пайплайн жив.
"""

import pytest
from pydantic import BaseModel, Field

from app.adapters.llm.fake import FakeLlm
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord


class Score(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200)


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


PV = PromptVersion(purpose="scoring", version=1)


async def test_valid_call_returns_model_and_records_llm_call() -> None:
    recorder = RecorderSpy()
    llm = FakeLlm(recorder=recorder, responses=['{"score": 87, "reason": "матч по стеку"}'])

    result = await llm.complete(
        purpose="scoring",
        prompt_version=PV,
        system="Ты оцениваешь вакансии.",
        data="Текст вакансии",
        response_model=Score,
    )

    assert result == Score(score=87, reason="матч по стеку")
    assert len(recorder.records) == 1
    call = recorder.records[0]
    assert call.purpose == "scoring"
    assert call.prompt_version == "scoring_v1"
    assert call.model == llm.model
    assert call.input_tokens > 0 and call.output_tokens > 0
    assert call.cost_usd > 0
    assert call.trace_id


async def test_invalid_output_retries_once_then_skips() -> None:
    recorder = RecorderSpy()
    llm = FakeLlm(
        recorder=recorder,
        responses=['{"score": 150, "reason": "вне диапазона"}', "не json"],
    )

    result = await llm.complete(
        purpose="scoring",
        prompt_version=PV,
        system="s",
        data="d",
        response_model=Score,
    )

    assert result is None  # graceful skip (R2)
    assert llm.attempts == 2  # ровно 1 retry
    assert len(recorder.records) == 1  # O1: учтён и неуспешный вызов


async def test_invalid_then_valid_recovers_on_retry() -> None:
    recorder = RecorderSpy()
    llm = FakeLlm(
        recorder=recorder,
        responses=["мусор", '{"score": 60, "reason": "ok"}'],
    )

    result = await llm.complete(
        purpose="scoring", prompt_version=PV, system="s", data="d", response_model=Score
    )

    assert result == Score(score=60, reason="ok")
    assert llm.attempts == 2


async def test_every_call_recorded() -> None:
    """O1: нет вызова без записи — 3 вызова → 3 записи."""
    recorder = RecorderSpy()
    llm = FakeLlm(recorder=recorder, responses=['{"score": 1, "reason": "r"}'] * 3)

    for _ in range(3):
        await llm.complete(
            purpose="scoring", prompt_version=PV, system="s", data="d", response_model=Score
        )

    assert len(recorder.records) == 3


async def test_fake_llm_never_raises_on_exhausted_responses() -> None:
    recorder = RecorderSpy()
    llm = FakeLlm(recorder=recorder, responses=[])

    result = await llm.complete(
        purpose="scoring", prompt_version=PV, system="s", data="d", response_model=Score
    )

    assert result is None
    assert len(recorder.records) == 1


@pytest.mark.parametrize("model_name", ["fake/model-a", "fake/model-b"])
async def test_model_name_configurable(model_name: str) -> None:
    """[R-C3]-механика: имя модели — параметр, не хардкод."""
    recorder = RecorderSpy()
    llm = FakeLlm(
        recorder=recorder, model=model_name, responses=['{"score": 5, "reason": "r"}']
    )

    await llm.complete(
        purpose="scoring", prompt_version=PV, system="s", data="d", response_model=Score
    )

    assert recorder.records[0].model == model_name
