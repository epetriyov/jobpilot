"""Фейковый LlmPort для тестов: детерминированные ответы, честный учёт llm_call (O1)."""

from __future__ import annotations

import time
from collections.abc import Sequence

import structlog
from pydantic import ValidationError

from app.domain.shared import PromptVersion
from app.obs.tracing import current_trace_id
from app.ports.llm import LlmCallRecord, LlmCallRecorderPort, T, wrap_untrusted_data

log = structlog.get_logger("adapters.llm.fake")

MAX_RETRIES = 1  # инвариант R2: ровно один валидационный retry


class FakeLlm:
    """Программируемый провайдер: очередь сырых ответов, по одному на попытку."""

    def __init__(
        self,
        *,
        recorder: LlmCallRecorderPort,
        responses: Sequence[str] = (),
        model: str = "fake/model",
        include_cost_in_usage: bool = True,
        price_per_mtok_in: float = 0.10,
        price_per_mtok_out: float = 0.40,
        fake_cost_usd: float = 0.000123,
        fake_input_tokens: int = 120,
        fake_output_tokens: int = 25,
    ) -> None:
        self._recorder = recorder
        self._responses = list(responses)
        self.model = model
        self._include_cost = include_cost_in_usage
        self._price_in = price_per_mtok_in
        self._price_out = price_per_mtok_out
        self._fake_cost = fake_cost_usd
        self._in_tokens = fake_input_tokens
        self._out_tokens = fake_output_tokens
        self.attempts = 0
        self.requested_models: list[str] = []
        self.sent_messages: list[dict[str, str]] = []

    async def complete(
        self,
        *,
        purpose: str,
        prompt_version: PromptVersion,
        system: str,
        data: str,
        response_model: type[T],
        few_shot: Sequence[tuple[str, str]] = (),
    ) -> T | None:
        started = time.perf_counter()
        self.sent_messages = _build_messages(system, data, few_shot)

        result: T | None = None
        attempts_left = 1 + MAX_RETRIES
        while attempts_left > 0 and self._responses:
            attempts_left -= 1
            self.attempts += 1
            self.requested_models.append(self.model)
            raw = self._responses.pop(0)
            try:
                result = response_model.model_validate_json(raw)
                break
            except ValidationError:
                log.warning("llm_invalid_output", purpose=purpose, model=self.model)
        else:
            if self.attempts == 0:
                # нет запрограммированных ответов — тоже graceful skip
                self.attempts += 1
                self.requested_models.append(self.model)
                log.warning("llm_no_response", purpose=purpose, model=self.model)

        if result is None:
            log.warning("llm_call_skipped", purpose=purpose, model=self.model)

        input_tokens = self._in_tokens * max(self.attempts, 1)
        output_tokens = self._out_tokens * max(self.attempts, 1)
        cost = (
            self._fake_cost
            if self._include_cost
            else input_tokens / 1_000_000 * self._price_in
            + output_tokens / 1_000_000 * self._price_out
        )
        await self._recorder.record(
            LlmCallRecord(
                purpose=purpose,
                model=self.model,
                prompt_version=prompt_version.as_str(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
                trace_id=current_trace_id(),
            )
        )
        return result


def _build_messages(
    system: str, data: str, few_shot: Sequence[tuple[str, str]]
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for user_example, assistant_example in few_shot:
        messages.append({"role": "user", "content": user_example})
        messages.append({"role": "assistant", "content": assistant_example})
    messages.append({"role": "user", "content": wrap_untrusted_data(data)})
    return messages
