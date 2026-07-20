"""LlmPort через instructor в openai-режиме поверх OpenRouter (AGENT_GUIDE.md §4).

Свап модели любого провайдера = смена строки в конфиге, код не меняется.
Валидационный ретрай instructor (max_retries=1), затем graceful skip (R2).
cost_usd — фактический из usage ответа OpenRouter; фолбэк — прайс конфига.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, cast

import instructor
import structlog
from openai import AsyncOpenAI

from app.config import Settings
from app.domain.shared import PromptVersion
from app.obs.metrics import record_llm_metrics
from app.obs.tracing import current_trace_id
from app.ports.llm import LlmCallRecord, LlmCallRecorderPort, T, wrap_untrusted_data

log = structlog.get_logger("adapters.llm.openrouter")

MAX_RETRIES = 1  # инвариант R2


class InstructorOpenRouterLlm:
    """Единый адаптер для всех моделей через OpenRouter (один ключ, OpenAI-совместимый API)."""

    def __init__(
        self,
        *,
        settings: Settings,
        recorder: LlmCallRecorderPort,
        purpose_models: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._recorder = recorder
        self._client = instructor.from_openai(
            AsyncOpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.openrouter_api_key.get_secret_value(),
            ),
            mode=instructor.Mode.JSON,
        )
        # модель per-purpose — только из конфига (хардкод = провал ревью)
        self._purpose_models = purpose_models or {
            "scoring": settings.llm_model_scoring,
            "summary": settings.llm_model_summary,
            "letter": settings.llm_model_letters,
            "invite": settings.llm_model_invite,
            "judge": settings.llm_model_judge,
        }

    def _model_for(self, purpose: str) -> str:
        return self._purpose_models.get(purpose, self._settings.llm_model_scoring)

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
        model = self._model_for(purpose)
        messages = _build_messages(system, data, few_shot)
        started = time.perf_counter()

        result: T | None = None
        completion = None
        try:
            raw, completion = await self._client.chat.completions.create_with_completion(
                model=model,
                response_model=response_model,
                messages=cast("Any", messages),
                max_retries=MAX_RETRIES,
                extra_body={"usage": {"include": True}},
            )
            # чистый экземпляр схемы: порт не протекает internals instructor (_raw_response)
            result = response_model.model_validate(raw.model_dump())
        except Exception:
            log.warning("llm_call_skipped", purpose=purpose, model=model)

        latency_ms = int((time.perf_counter() - started) * 1000)
        in_tokens, out_tokens, cost = self._usage(completion, model)
        await self._recorder.record(
            LlmCallRecord(
                purpose=purpose,
                model=model,
                prompt_version=prompt_version.as_str(),
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                trace_id=current_trace_id(),
            )
        )
        record_llm_metrics(
            purpose=purpose,
            model=model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=cost,
        )
        return result

    def _usage(self, completion: object, model: str) -> tuple[int, int, float]:
        usage = getattr(completion, "usage", None)
        in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = getattr(usage, "cost", None)
        if cost is None:
            cost = (
                in_tokens / 1_000_000 * self._settings.price_per_mtok_in
                + out_tokens / 1_000_000 * self._settings.price_per_mtok_out
            )
        return in_tokens, out_tokens, float(cost)


def _build_messages(
    system: str, data: str, few_shot: Sequence[tuple[str, str]]
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for user_example, assistant_example in few_shot:
        messages.append({"role": "user", "content": user_example})
        messages.append({"role": "assistant", "content": assistant_example})
    messages.append({"role": "user", "content": wrap_untrusted_data(data)})
    return messages
