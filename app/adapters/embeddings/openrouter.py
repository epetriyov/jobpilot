"""EmbeddingPort через OpenAI-совместимый /embeddings поверх OpenRouter.

Свап модели = строка конфига `LLM_MODEL_EMBEDDING`, код не меняется. Каждый вызов
пишет `llm_call` (purpose=`embedding`, O1); cost — из usage при наличии, иначе прайс
конфига (у эмбеддингов только input-токены). Сбой провайдера → исключение наверх
(вызывающий backfill/selector решает, фолбэкать ли на recent).
"""

from __future__ import annotations

import time

import structlog
from openai import AsyncOpenAI

from app.config import Settings
from app.obs.metrics import record_llm_metrics
from app.obs.tracing import current_trace_id
from app.ports.embeddings import EMBEDDING_DIM, EMBEDDING_PROMPT_VERSION
from app.ports.llm import LlmCallRecord, LlmCallRecorderPort

log = structlog.get_logger("adapters.embeddings.openrouter")


class OpenRouterEmbedder:
    def __init__(
        self,
        *,
        settings: Settings,
        recorder: LlmCallRecorderPort,
        model: str | None = None,
    ) -> None:
        self._settings = settings
        self._recorder = recorder
        self.model = model or settings.llm_model_embedding
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.openrouter_api_key.get_secret_value(),
        )

    async def embed(self, text: str) -> list[float]:
        started = time.perf_counter()
        # dimensions привязан к контракту схемы (labeled_vacancy.embedding vector(768)):
        # provider-модели text-embedding-3-* отдают 1536 по умолчанию и не влезли бы в
        # колонку — усечение matryoshka до EMBEDDING_DIM держит вектор совместимым.
        response = await self._client.embeddings.create(
            model=self.model, input=text, dimensions=EMBEDDING_DIM
        )
        vector = [float(x) for x in response.data[0].embedding]

        usage = getattr(response, "usage", None)
        in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        cost = in_tokens / 1_000_000 * self._settings.price_per_mtok_in

        await self._recorder.record(
            LlmCallRecord(
                purpose="embedding",
                model=self.model,
                prompt_version=EMBEDDING_PROMPT_VERSION.as_str(),
                input_tokens=in_tokens,
                output_tokens=0,
                cost_usd=cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
                trace_id=current_trace_id(),
            )
        )
        record_llm_metrics(
            purpose="embedding",
            model=self.model,
            input_tokens=in_tokens,
            output_tokens=0,
            cost_usd=cost,
        )
        return vector
