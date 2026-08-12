"""Repository-порты минимального слоя хранения (contracts/repositories.md)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.domain.relevance import LabeledVacancy, Score, VacancySnapshot
from app.domain.shared import SourceRef
from app.domain.sourcing import Vacancy

__all__ = [
    "DigestRepositoryPort",
    "JobRunRepositoryPort",
    "LabelRepositoryPort",
    "LabeledVacancy",
    "ScoredCandidate",
    "ScoringRepositoryPort",
    "ScraperApprovalPort",
    "SeenVacancyRepositoryPort",
]


class ScoredCandidate(BaseModel):
    """Кандидат дайджеста: снапшот + скор + отображаемая вилка."""

    model_config = ConfigDict(frozen=True)

    snapshot: VacancySnapshot
    score: Score
    salary_text: str | None = None


class ScoringRepositoryPort(Protocol):
    """Рабочие операции скоринга поверх реестра seen (data-model этапа 1, R1)."""

    async def unscored(self, prompt_version: str, limit: int = 200) -> list[VacancySnapshot]:
        """Виденные без актуального скора текущей prompt_version (R1)."""
        ...

    async def save_score(self, ref: SourceRef, score: Score) -> None: ...

    async def unsent_scored(self) -> list[ScoredCandidate]:
        """Скоренные, ещё не уходившие в дайджест (digest_sent_at IS NULL)."""
        ...

    async def snapshot(self, ref: SourceRef) -> VacancySnapshot | None:
        """Снапшот виденной вакансии — разметка без похода в источник (этап 1)."""
        ...


class SeenVacancyRepositoryPort(Protocol):
    async def is_seen(self, ref: SourceRef) -> bool: ...

    async def mark_seen(self, vacancy: Vacancy) -> None:
        """Идемпотентно: повторный вызов не меняет first_seen_at (S1)."""
        ...

    async def find_duplicate(self, normalized_key: str, within_days: int = 30) -> str | None:
        """source_ref-ключ оригинала для кросс-источникового дедупа (S2)."""
        ...

    async def mark_digest_sent(self, refs: Sequence[SourceRef], at: datetime) -> None: ...


class DigestRepositoryPort(SeenVacancyRepositoryPort, ScoringRepositoryPort, Protocol):
    """Совмещённый порт для RunDailyDigest (реализуется одним репозиторием seen)."""


class LabelRepositoryPort(Protocol):
    async def upsert(self, labeled: LabeledVacancy) -> None:
        """Вердикт по source_ref: повторная разметка обновляет, не дублирует."""
        ...

    async def recent(self, limit: int = 10) -> list[LabeledVacancy]:
        """Few-shot «последние N» (R3)."""
        ...

    async def counts(self) -> tuple[int, int]:
        """(relevant, irrelevant) — прогресс разметки для /train."""
        ...


class DatasetAppenderPort(Protocol):
    """Append-only строка eval-датасета (Приложение TEST_CASES.md)."""

    def append(self, example: dict) -> None: ...  # type: ignore[type-arg]


class ScraperApprovalPort(Protocol):
    """Персист факта `/approve_scraper <site>` (этап 5, data-model.md).

    Служебный флаг источника (не доменный агрегат): сайт из SITES_CANARY без
    одобрения → секция «На проверку»; одобренный → основной поток (FR-007).
    """

    async def is_approved(self, site: str) -> bool: ...

    async def approve(self, site: str, chat_id: int) -> None:
        """Идемпотентно: повторный approve не меняет момент первого одобрения."""
        ...

    async def approved_sites(self) -> set[str]: ...


class JobRunRepositoryPort(Protocol):
    async def start(self, job_name: str, trace_id: str) -> int: ...

    async def finish(
        self,
        run_id: int,
        *,
        status: Literal["success", "partial", "error"],
        items_in: int = 0,
        items_out: int = 0,
        error: str | None = None,
    ) -> None: ...
