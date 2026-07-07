"""[R-C2] Единый contract-suite LlmPort, параметризованный по адаптерам.

Одинаковые входы → валидная pydantic-схема на выходе; валидационный retry ровно 1,
затем graceful skip; каждый адаптер пишет llm_call; cost_usd — из usage ответа
(фолбэк — прайс конфига); [R-C3] свап модели строкой конфига без изменения кода.

instructor_openrouter гоняется на записанных ответах (respx) — без ключей и сети.
"""

import json
from pathlib import Path
from typing import Any, Protocol

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from app.adapters.llm.fake import FakeLlm
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.config import Settings
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord, LlmPort

GOLDEN = Path(__file__).parent.parent / "golden" / "openrouter"
PV = PromptVersion(purpose="scoring", version=1)
BASE_URL = "https://openrouter.ai/api/v1"


class Score(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200)


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


def make_settings(**env_overrides: str) -> Settings:
    env = {
        "TELEGRAM_API_TOKEN": "123456:contract-tg-token",
        "OWNER_CHAT_ID": "1",
        "OPENROUTER_API_KEY": "sk-or-contract-key",
        "POSTGRES_DSN": "postgresql+psycopg://u:p@localhost/db",
        **env_overrides,
    }
    import os

    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        return Settings.load(env_file=None)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN / name).read_text())  # type: ignore[no-any-return]


class Harness(Protocol):
    """Адаптер-специфичная обвязка suite: собрать порт с заданной очередью ответов."""

    recorder: RecorderSpy

    def make(self, responses: list[str], *, with_cost: bool = True) -> LlmPort: ...

    def attempts(self) -> int: ...

    def requested_models(self) -> list[str]: ...

    def sent_messages(self) -> list[dict[str, Any]]: ...


class FakeHarness:
    def __init__(self, settings: Settings) -> None:
        self.recorder = RecorderSpy()
        self._llm: FakeLlm | None = None
        self._settings = settings

    def make(self, responses: list[str], *, with_cost: bool = True) -> LlmPort:
        self._llm = FakeLlm(
            recorder=self.recorder,
            model=self._settings.llm_model_scoring,
            responses=responses,
            include_cost_in_usage=with_cost,
            price_per_mtok_in=self._settings.price_per_mtok_in,
            price_per_mtok_out=self._settings.price_per_mtok_out,
        )
        return self._llm

    def attempts(self) -> int:
        assert self._llm is not None
        return self._llm.attempts

    def requested_models(self) -> list[str]:
        assert self._llm is not None
        return self._llm.requested_models

    def sent_messages(self) -> list[dict[str, Any]]:
        assert self._llm is not None
        return self._llm.sent_messages


class OpenRouterHarness:
    def __init__(self, settings: Settings, router: respx.MockRouter) -> None:
        self.recorder = RecorderSpy()
        self._settings = settings
        self._router = router
        self._route: respx.Route | None = None

    def make(self, responses: list[str], *, with_cost: bool = True) -> LlmPort:
        template = golden("score_valid.json" if with_cost else "score_valid_no_cost.json")
        payloads = []
        for content in responses:
            payload = json.loads(json.dumps(template))
            payload["choices"][0]["message"]["content"] = content
            payloads.append(httpx.Response(200, json=payload))
        self._route = self._router.post("/api/v1/chat/completions").mock(
            side_effect=payloads or [httpx.Response(500)]
        )
        return InstructorOpenRouterLlm(settings=self._settings, recorder=self.recorder)

    def attempts(self) -> int:
        assert self._route is not None
        return self._route.call_count

    def requested_models(self) -> list[str]:
        assert self._route is not None
        return [
            json.loads(call.request.content)["model"] for call in self._route.calls
        ]

    def sent_messages(self) -> list[dict[str, Any]]:
        assert self._route is not None
        return list(json.loads(self._route.calls[0].request.content)["messages"])


@pytest.fixture(params=["fake", "instructor_openrouter"])
def harness(request: pytest.FixtureRequest) -> Any:
    settings = make_settings()
    if request.param == "fake":
        yield FakeHarness(settings)
    else:
        with respx.mock(base_url="https://openrouter.ai") as router:
            yield OpenRouterHarness(settings, router)


VALID = '{"score": 87, "reason": "матч по стеку"}'
INVALID = '{"score": 150, "reason": "вне диапазона"}'


async def _complete(llm: LlmPort) -> Score | None:
    return await llm.complete(
        purpose="scoring",
        prompt_version=PV,
        system="Ты оцениваешь релевантность вакансии.",
        data="Текст вакансии для анализа",
        response_model=Score,
    )


async def test_valid_output_matches_schema(harness: Harness) -> None:
    llm = harness.make([VALID])
    result = await _complete(llm)
    assert result == Score(score=87, reason="матч по стеку")


async def test_retry_exactly_once_then_skip(harness: Harness) -> None:
    llm = harness.make([INVALID, INVALID])
    result = await _complete(llm)
    assert result is None
    assert harness.attempts() == 2


async def test_recovers_after_single_retry(harness: Harness) -> None:
    llm = harness.make([INVALID, VALID])
    result = await _complete(llm)
    assert result is not None
    assert harness.attempts() == 2


async def test_llm_call_recorded_with_cost_from_usage(harness: Harness) -> None:
    llm = harness.make([VALID], with_cost=True)
    await _complete(llm)

    assert len(harness.recorder.records) == 1
    call = harness.recorder.records[0]
    assert call.purpose == "scoring"
    assert call.prompt_version == "scoring_v1"
    assert call.input_tokens > 0
    assert call.cost_usd == pytest.approx(0.000123)  # фактический из usage
    assert call.trace_id


async def test_cost_fallback_to_config_price(harness: Harness) -> None:
    llm = harness.make([VALID], with_cost=False)
    await _complete(llm)

    call = harness.recorder.records[0]
    # golden usage: 120 in / 25 out; прайс конфига 0.10/0.40 $ за 1M токенов
    expected = 120 / 1_000_000 * 0.10 + 25 / 1_000_000 * 0.40
    assert call.cost_usd == pytest.approx(expected)


async def test_skipped_call_still_recorded(harness: Harness) -> None:
    """O1: учёт есть и у неуспешного вызова."""
    llm = harness.make([INVALID, INVALID])
    await _complete(llm)
    assert len(harness.recorder.records) == 1


async def test_model_comes_from_config(harness: Harness) -> None:
    """[R-C3] Свап модели = смена строки конфига, без изменения кода."""
    llm = harness.make([VALID])
    await _complete(llm)
    assert harness.requested_models() == ["google/gemini-2.5-flash-lite"]
    assert harness.recorder.records[0].model == "google/gemini-2.5-flash-lite"


async def test_data_wrapped_as_untrusted_block(harness: Harness) -> None:
    """R5: внешний текст — внутри data-блока, не на уровне system."""
    llm = harness.make([VALID])
    await _complete(llm)

    messages = harness.sent_messages()
    system_texts = [m["content"] for m in messages if m["role"] == "system"]
    user_texts = [m["content"] for m in messages if m["role"] == "user"]

    assert all("Текст вакансии для анализа" not in t for t in system_texts)
    data_messages = [t for t in user_texts if "Текст вакансии для анализа" in t]
    assert len(data_messages) == 1
    assert "<data>" in data_messages[0] and "</data>" in data_messages[0]
    assert "не инструкции" in data_messages[0]
