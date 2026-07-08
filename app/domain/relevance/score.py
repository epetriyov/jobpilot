"""Score — оценка релевантности (DOMAIN.md §3.2, инвариант R2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Score(BaseModel):
    """Выход скоринга: строгая схема, невалидное значение режется на границе (R2)."""

    model_config = ConfigDict(frozen=True)

    value: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200)
    prompt_version: str
    model: str


class LlmScore(BaseModel):
    """Схема ответа LLM (response_model): только то, что генерирует модель."""

    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200)
