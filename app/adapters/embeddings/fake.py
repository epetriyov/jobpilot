"""Детерминированный FakeEmbedder: хеш-мешок слов + честный учёт llm_call (O1).

Один и тот же текст → один и тот же вектор; общие токены двух текстов повышают их
косинусную близость — этого достаточно, чтобы семантический селектор и сравнительный
eval работали в fake-режиме (без ключей и сети). Реальные эмбеддинги — OpenRouterEmbedder.
"""

from __future__ import annotations

import hashlib
import math
import re
import time

import structlog

from app.obs.metrics import record_llm_metrics
from app.obs.tracing import current_trace_id
from app.ports.embeddings import EMBEDDING_DIM, EMBEDDING_PROMPT_VERSION
from app.ports.llm import LlmCallRecord, LlmCallRecorderPort

log = structlog.get_logger("adapters.embeddings.fake")

_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class FakeEmbedder:
    """Хеширующий векторизатор: токен → индекс+знак; L2-нормализация."""

    def __init__(
        self,
        *,
        recorder: LlmCallRecorderPort,
        model: str = "fake/embedding-stub",
        dim: int = EMBEDDING_DIM,
        fake_cost_usd: float = 0.000001,
    ) -> None:
        self._recorder = recorder
        self.model = model
        self._dim = dim
        self._fake_cost = fake_cost_usd

    async def embed(self, text: str) -> list[float]:
        started = time.perf_counter()
        tokens = _tokens(text)
        vec = [0.0] * self._dim
        for tok in tokens:
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = [v / norm for v in vec]

        input_tokens = max(len(tokens), 1)
        await self._recorder.record(
            LlmCallRecord(
                purpose="embedding",
                model=self.model,
                prompt_version=EMBEDDING_PROMPT_VERSION.as_str(),
                input_tokens=input_tokens,
                output_tokens=0,
                cost_usd=self._fake_cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
                trace_id=current_trace_id(),
            )
        )
        record_llm_metrics(
            purpose="embedding",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=0,
            cost_usd=self._fake_cost,
        )
        return vec
