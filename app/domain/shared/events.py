"""Базовое доменное событие."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    occurred_at: datetime = Field(default_factory=_utcnow)
