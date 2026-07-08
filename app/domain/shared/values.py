"""Value objects shared kernel (DOMAIN.md §1, §3.1)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Source(StrEnum):
    """Откуда пришла вакансия (DOMAIN.md §1)."""

    HH = "hh"
    GETMATCH = "getmatch"
    SITE = "site"
    MANUAL = "manual"


class SourceRef(BaseModel):
    """Уникальный адрес вакансии: (source, site_name?, external_id)."""

    model_config = ConfigDict(frozen=True)

    source: Source
    site_name: str | None = None
    external_id: str

    @model_validator(mode="after")
    def _site_name_consistency(self) -> SourceRef:
        if self.source is Source.SITE and not self.site_name:
            raise ValueError("site_name обязателен для source=site")
        if self.source is not Source.SITE and self.site_name is not None:
            raise ValueError("site_name допустим только для source=site")
        return self

    def as_key(self) -> str:
        if self.site_name is not None:
            return f"{self.source}:{self.site_name}:{self.external_id}"
        return f"{self.source}:{self.external_id}"


class Salary(BaseModel):
    """Зарплатная вилка; все поля опциональны — публикуется не везде."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    from_: int | None = Field(None, alias="from")
    to: int | None = None
    currency: str | None = None


class PromptVersion(BaseModel):
    """Версионируемый промпт: purpose + номер версии (constitution III)."""

    model_config = ConfigDict(frozen=True)

    purpose: str
    version: int

    def as_str(self) -> str:
        return f"{self.purpose}_v{self.version}"
