"""Контекст CRM (DOMAIN.md §3.3): агрегат Application, статусная машина, раунды."""

from app.domain.crm.application import (
    Application,
    ApplicationStatus,
    IllegalTransition,
    InterviewRound,
    InterviewRoundKind,
    InterviewScheduled,
    RejectStage,
    StatusChanged,
    VacancySaved,
)

__all__ = [
    "Application",
    "ApplicationStatus",
    "IllegalTransition",
    "InterviewRound",
    "InterviewRoundKind",
    "InterviewScheduled",
    "RejectStage",
    "StatusChanged",
    "VacancySaved",
]
