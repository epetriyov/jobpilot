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
    """Схема ответа LLM (response_model): только то, что генерирует модель.

    R2 (уточнено 2026-07-17 на реальном Gemini): выход из диапазона score — реджект+skip,
    но многословный reason НЕ повод терять вакансию — терпим до 2000 и обрезаем до 200
    при сохранении в доменный Score. `score` остаётся строгим инвариантом.
    """

    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=2000)

    def to_reason(self) -> str:
        return self.reason[:200]
