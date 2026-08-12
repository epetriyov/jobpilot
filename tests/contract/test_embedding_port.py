"""[T6D-1] Contract-suite EmbeddingPort по адаптерам (fake + openrouter).

Инварианты: вектор длины EMBEDDING_DIM (768); детерминизм (один текст → один вектор);
каждый вызов пишет llm_call с purpose=`embedding` (O1); openrouter гоняется на
записанном ответе (respx) — без ключей и сети.
"""

from __future__ import annotations

import os

import httpx
import pytest
import respx

from app.adapters.embeddings.fake import FakeEmbedder
from app.adapters.embeddings.openrouter import OpenRouterEmbedder
from app.config import Settings
from app.ports.embeddings import EMBEDDING_DIM
from app.ports.llm import LlmCallRecord


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


def _embedding_response(dim: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": [{"object": "embedding", "index": 0, "embedding": [0.01] * dim}],
            "model": "google/text-embedding-004",
            "usage": {"prompt_tokens": 7, "total_tokens": 7},
        },
    )


async def test_fake_returns_correct_dimension() -> None:
    embedder = FakeEmbedder(recorder=RecorderSpy())
    vec = await embedder.embed("Engineering Manager, Python, найм лидов")
    assert len(vec) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in vec)


async def test_fake_is_deterministic() -> None:
    embedder = FakeEmbedder(recorder=RecorderSpy())
    a = await embedder.embed("одинаковый текст вакансии")
    b = await embedder.embed("одинаковый текст вакансии")
    assert a == b


async def test_fake_similar_texts_closer_than_unrelated() -> None:
    """Хеш-мешок слов: общие токены → выше косинусная близость (нужно селектору)."""
    embedder = FakeEmbedder(recorder=RecorderSpy())
    query = await embedder.embed("Python highload найм лидов backend")
    similar = await embedder.embed("backend Python найм highload инженеров")
    unrelated = await embedder.embed("продажи недвижимости холодные звонки")

    def dot(x: list[float], y: list[float]) -> float:
        return sum(a * b for a, b in zip(x, y, strict=True))

    assert dot(query, similar) > dot(query, unrelated)


async def test_fake_records_llm_call_with_embedding_purpose() -> None:
    recorder = RecorderSpy()
    embedder = FakeEmbedder(recorder=recorder)
    await embedder.embed("любой текст")
    assert len(recorder.records) == 1
    call = recorder.records[0]
    assert call.purpose == "embedding"
    assert call.prompt_version == "embedding_v1"
    assert call.input_tokens > 0
    assert call.trace_id is not None


async def test_openrouter_returns_dimension_and_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_FAKE", raising=False)
    settings = make_settings()
    recorder = RecorderSpy()
    with respx.mock(base_url="https://openrouter.ai") as router:
        router.post("/api/v1/embeddings").mock(side_effect=[_embedding_response(EMBEDDING_DIM)])
        embedder = OpenRouterEmbedder(settings=settings, recorder=recorder)
        vec = await embedder.embed("текст для эмбеддинга")

    assert len(vec) == EMBEDDING_DIM
    assert len(recorder.records) == 1
    call = recorder.records[0]
    assert call.purpose == "embedding"
    assert call.input_tokens == 7
    assert call.model == settings.llm_model_embedding


async def test_openrouter_model_from_config() -> None:
    settings = make_settings(LLM_MODEL_EMBEDDING="vendor/custom-embed")
    recorder = RecorderSpy()
    with respx.mock(base_url="https://openrouter.ai") as router:
        route = router.post("/api/v1/embeddings").mock(
            side_effect=[_embedding_response(EMBEDDING_DIM)]
        )
        embedder = OpenRouterEmbedder(settings=settings, recorder=recorder)
        await embedder.embed("текст")

    import json

    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "vendor/custom-embed"
    assert recorder.records[0].model == "vendor/custom-embed"
