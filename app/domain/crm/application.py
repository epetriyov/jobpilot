"""Агрегат Application и статусная машина CRM (DOMAIN.md §3.3).

Единственный источник истины по переходам — §3.3. Правила живут в домене
(методы агрегата), не в if-ах бота: переходы только вперёд, раунды строго по
возрастанию только в статусе interview, отказ требует валидного stage.
Инвариант C1 (один активный Application на вакансию) держит БД (unique vacancy_id).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.shared import DomainEvent


class IllegalTransition(Exception):
    """Недопустимый переход/действие (C2); состояние агрегата не меняется.

    Единое имя с networking §3.5 — единообразие вежливого отказа в боте.
    """


class ApplicationStatus(StrEnum):
    """Воронка заявки: только вперёд new→applied→interview→offer|rejected (§3.3)."""

    NEW = "new"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"


class RejectStage(StrEnum):
    """Этап, на котором пришёл отказ (§3.3)."""

    PRE_HR = "pre_hr"
    HR = "hr"
    TECH = "tech"
    FINAL = "final"


class InterviewRoundKind(StrEnum):
    """Раунды собеседования, упорядочены hr → tech-1 → … → final (§3.3, C2)."""

    HR = "hr"
    TECH_1 = "tech-1"
    TECH_2 = "tech-2"
    TECH_3 = "tech-3"
    FINAL = "final"

    @staticmethod
    def rank(kind: InterviewRoundKind) -> int:
        """Ранг порядка: hr < tech-1 < tech-2 < tech-3 < final (final всегда последний)."""
        return _ROUND_RANK[kind]


_ROUND_RANK: dict[InterviewRoundKind, int] = {
    InterviewRoundKind.HR: 0,
    InterviewRoundKind.TECH_1: 10,
    InterviewRoundKind.TECH_2: 20,
    InterviewRoundKind.TECH_3: 30,
    InterviewRoundKind.FINAL: 100,
}

# §3.3: линейные переходы вперёд (reject — отдельный путь, требует stage).
_LINEAR_NEXT: dict[ApplicationStatus, ApplicationStatus] = {
    ApplicationStatus.NEW: ApplicationStatus.APPLIED,
    ApplicationStatus.APPLIED: ApplicationStatus.INTERVIEW,
    ApplicationStatus.INTERVIEW: ApplicationStatus.OFFER,
}

# §3.3: допустимые этапы отказа по источнику.
_REJECT_STAGES_BY_SOURCE: dict[ApplicationStatus, frozenset[RejectStage]] = {
    ApplicationStatus.NEW: frozenset({RejectStage.PRE_HR, RejectStage.HR}),
    ApplicationStatus.APPLIED: frozenset({RejectStage.PRE_HR, RejectStage.HR}),
    ApplicationStatus.INTERVIEW: frozenset({RejectStage.HR, RejectStage.TECH, RejectStage.FINAL}),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InterviewRound(BaseModel):
    """VO раунда: вид, порядковый номер (монотонный в пределах заявки), время (C2)."""

    model_config = ConfigDict(frozen=True)

    kind: InterviewRoundKind
    ordinal: int
    at: datetime


class VacancySaved(DomainEvent):
    """💾 Сохранить: создан Application(new) на вакансию (§3.3)."""

    vacancy_id: int


class StatusChanged(DomainEvent):
    """Смена статуса заявки (§3.3): from → to."""

    vacancy_id: int
    from_status: ApplicationStatus
    to_status: ApplicationStatus


class InterviewScheduled(DomainEvent):
    """Добавлен раунд собеседования (§3.3)."""

    vacancy_id: int
    kind: InterviewRoundKind
    ordinal: int


class Application(BaseModel):
    """Агрегат заявки (root): статусная машина §3.3 как доменные методы.

    Один активный Application на вакансию (C1) гарантирует БД (unique vacancy_id);
    удаление — DELETE строки (не переход), освобождает вакансию для нового 💾.
    """

    model_config = ConfigDict(validate_assignment=True)

    vacancy_id: int
    status: ApplicationStatus = ApplicationStatus.NEW
    interview_rounds: list[InterviewRound] = Field(default_factory=list)
    reject_stage: RejectStage | None = None
    interview_url: str | None = None
    notes: str | None = None

    @classmethod
    def create(cls, *, vacancy_id: int) -> tuple[Application, VacancySaved]:
        """💾 Сохранить: заявка в статусе new + событие VacancySaved ([C-U4])."""
        return cls(vacancy_id=vacancy_id), VacancySaved(vacancy_id=vacancy_id)

    def transition(self, to: ApplicationStatus) -> StatusChanged:
        """Линейный переход вперёд (§3.3); иначе IllegalTransition, состояние неизменно."""
        if _LINEAR_NEXT.get(self.status) is not to:
            raise IllegalTransition(f"{self.status} → {to} запрещён (§3.3)")
        frm = self.status
        self.status = to
        return StatusChanged(vacancy_id=self.vacancy_id, from_status=frm, to_status=to)

    def apply(self) -> StatusChanged:
        """new → applied."""
        return self.transition(ApplicationStatus.APPLIED)

    def to_interview(self) -> StatusChanged:
        """applied → interview."""
        return self.transition(ApplicationStatus.INTERVIEW)

    def to_offer(self) -> StatusChanged:
        """interview → offer (терминальный)."""
        return self.transition(ApplicationStatus.OFFER)

    def add_round(
        self, kind: InterviewRoundKind, *, at: datetime | None = None
    ) -> InterviewScheduled:
        """C2: раунд только в interview, строго по возрастанию ранга; иначе IllegalTransition."""
        if self.status is not ApplicationStatus.INTERVIEW:
            raise IllegalTransition(f"раунд вне статуса interview ({self.status}) запрещён (C2)")
        last_rank = (
            InterviewRoundKind.rank(self.interview_rounds[-1].kind)
            if (self.interview_rounds)
            else -1
        )
        if InterviewRoundKind.rank(kind) <= last_rank:
            raise IllegalTransition(f"раунд {kind} не по возрастанию (C2)")
        ordinal = len(self.interview_rounds) + 1
        # validate_assignment требует переприсвоить список целиком
        self.interview_rounds = [
            *self.interview_rounds,
            InterviewRound(kind=kind, ordinal=ordinal, at=at or _utcnow()),
        ]
        return InterviewScheduled(vacancy_id=self.vacancy_id, kind=kind, ordinal=ordinal)

    def reject(self, stage: RejectStage | None) -> StatusChanged:
        """Отказ (§3.3): stage обязателен и валиден по источнику; иначе IllegalTransition."""
        allowed = _REJECT_STAGES_BY_SOURCE.get(self.status)
        if allowed is None:
            raise IllegalTransition(f"отказ из терминального {self.status} запрещён (§3.3)")
        if stage is None:
            raise IllegalTransition("отказ без stage запрещён ([C-U3])")
        if stage not in allowed:
            raise IllegalTransition(f"stage {stage} недопустим из {self.status} ([C-U3])")
        frm = self.status
        self.reject_stage = stage
        self.status = ApplicationStatus.REJECTED
        return StatusChanged(
            vacancy_id=self.vacancy_id, from_status=frm, to_status=ApplicationStatus.REJECTED
        )

    def add_interview_details(self, *, url: str | None = None, notes: str | None = None) -> None:
        """C3: дополняет interview_url/notes, статус НЕ меняет (ручной путь 6B, LLM — 6G)."""
        if url is not None:
            self.interview_url = url
        if notes is not None:
            self.notes = notes if not self.notes else f"{self.notes}\n{notes}"
