"""Repository-порты минимального слоя хранения (contracts/repositories.md)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.domain.correspondence import CoverLetter
from app.domain.crm import Application
from app.domain.relevance import LabeledVacancy, Score, VacancySnapshot
from app.domain.shared import SourceRef
from app.domain.sourcing import Vacancy

__all__ = [
    "ApplicationRepositoryPort",
    "CostTotals",
    "CoverLetterRepositoryPort",
    "DigestRepositoryPort",
    "JobRunRepositoryPort",
    "LabelRepositoryPort",
    "LabeledVacancy",
    "LlmCostReaderPort",
    "ScoredCandidate",
    "ScoringRepositoryPort",
    "ScraperApprovalPort",
    "SeenVacancyRepositoryPort",
    "VacancyCounts",
    "VacancyListFilter",
    "VacancyReaderPort",
    "VacancyRecord",
    "VacancyRepositoryPort",
    "VacancyStatsReaderPort",
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


class VacancyRecord(BaseModel):
    """Строка хранилища `vacancy` для чтения CRM/MCP/аналитикой (этап 6A).

    `id` — ключ, на который ссылается `application.vacancy_id`; наружу отдаётся
    доменный `SourceRef`, снапшот и скор, без ORM.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    source_ref: SourceRef
    title: str
    company: str
    url: str
    description_text: str
    salary_text: str | None = None
    score: int | None = None
    score_reason: str | None = None
    duplicate_of: str | None = None
    canary: bool = False
    first_seen_at: datetime


class VacancyListFilter(BaseModel):
    """Фильтр выборки хранилища для списков CRM/MCP/аналитики."""

    model_config = ConfigDict(frozen=True)

    scored_only: bool = False
    min_score: int | None = None
    limit: int = 50


class VacancyRepositoryPort(Protocol):
    """Чтение полного хранилища `vacancy` (этап 6A) — фундамент CRM/MCP/аналитики.

    Надстройка над реестром seen: сигнатуры дедуп/скоринга не меняются, здесь —
    доступ по ключам и поиск для карточек заявок, писем, MCP-инструментов.
    """

    async def get(self, source_ref: SourceRef) -> VacancyRecord | None:
        """Строка по SourceRef (S1-ключ) — None, если вакансия не виделась."""
        ...

    async def get_by_id(self, vacancy_id: int) -> VacancyRecord | None:
        """Строка по PK — ключ связи с `application.vacancy_id`."""
        ...

    async def list(self, filter_: VacancyListFilter) -> Sequence[VacancyRecord]:
        """Список (новейшие первыми) с фильтром по скору — для /saved, MCP, аналитики."""
        ...

    async def search_saved(self, query: str) -> Sequence[VacancyRecord]:
        """Поиск по title/company/описанию (регистронезависимо) — MCP `search_saved`."""
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
    async def upsert(self, labeled: LabeledVacancy, embedding: list[float] | None = None) -> None:
        """Вердикт по source_ref: повторная разметка обновляет, не дублирует.

        `embedding` (этап 6D) — вектор снапшота для семантического few-shot; None
        оставляет колонку как есть (наполнит backfill-джоб).
        """
        ...

    async def recent(self, limit: int = 10) -> list[LabeledVacancy]:
        """Few-shot «последние N» (R3)."""
        ...

    async def nearest(self, embedding: list[float], k: int = 10) -> list[LabeledVacancy]:
        """Few-shot по семантической близости (pgvector `<=>`, cosine; этап 6D)."""
        ...

    async def missing_embeddings(self, limit: int = 200) -> list[LabeledVacancy]:
        """Размеченные без эмбеддинга — вход идемпотентного backfill-джоба (6D)."""
        ...

    async def set_embedding(self, source_ref: SourceRef, embedding: list[float]) -> None:
        """Записать эмбеддинг для размеченной вакансии по source_ref (6D)."""
        ...

    async def embedded_count(self) -> int:
        """Сколько размеченных уже с эмбеддингом — порог фолбэка семантики (6D)."""
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


class ApplicationRepositoryPort(Protocol):
    """Хранилище заявок CRM (data-model §2). Один активный на вакансию — C1 (unique)."""

    async def get_by_vacancy(self, vacancy_id: int) -> Application | None: ...

    async def save(self, app: Application) -> int:
        """Upsert по vacancy_id (C1): создаёт или обновляет заявку и её раунды."""
        ...

    async def delete(self, vacancy_id: int) -> None:
        """🗑 hard-delete из любого статуса (не переход); освобождает вакансию (C1)."""
        ...

    async def list_all(self) -> list[Application]:
        """Все заявки для `/saved`."""
        ...

    async def funnel_counts(self) -> dict[str, int]:
        """Воронка по статусам для `/stats` (6C)."""
        ...


# --- Аналитика (этап 6C): /stats, /costs, /review ---


class VacancyCounts(BaseModel):
    """Счётчики хранилища `vacancy` для /stats: всего и скоренных (R1)."""

    model_config = ConfigDict(frozen=True)

    total: int
    scored: int


class VacancyStatsReaderPort(Protocol):
    """Аналитические чтения хранилища `vacancy` (этап 6C) — надстройка, сигнатуры
    дедупа/скоринга и VacancyRepositoryPort не меняет."""

    async def counts(self) -> VacancyCounts:
        """(всего, скоренных) — счётчики для /stats."""
        ...

    async def random_scored(self, limit: int) -> Sequence[VacancyRecord]:
        """N случайных скоренных вакансий — вход /review (agreement rate)."""
        ...


class CostTotals(BaseModel):
    """Агрегат `llm_call` за период для /costs (инвариант O1)."""

    model_config = ConfigDict(frozen=True)

    total_usd: float
    input_tokens: int
    output_tokens: int
    calls: int
    by_purpose: dict[str, float]


class LlmCostReaderPort(Protocol):
    """Чтение затрат LLM за период (`/costs`, сверка с Langfuse ±5%, [C-I2])."""

    async def totals(self, since: datetime, until: datetime) -> CostTotals:
        """Сумма cost_usd/токенов и разбивка по purpose за окно [since, until]."""
        ...


class VacancyReaderPort(Protocol):
    """Чтение снапшота вакансии по числовому id — источник фактов для карточек/писем.

    Надстройка над хранилищем vacancy (под-этап 6A `VacancyRepository.get_by_id`);
    в 6E используется генератором письма. Возвращает None, если вакансии нет.
    """

    async def get_by_id(self, vacancy_id: int) -> VacancyRecord | None: ...


class CoverLetterRepositoryPort(Protocol):
    """История сопроводительных писем вакансии (data-model §4, под-этап 6E).

    Несколько версий на вакансию: 🔁/✏️ добавляют новую строку, `latest` — актуальная.
    """

    async def add(self, letter: CoverLetter) -> int: ...

    async def latest(self, vacancy_id: int) -> CoverLetter | None: ...


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
