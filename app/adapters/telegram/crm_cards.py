"""CRM в Telegram: карточка `/saved`, кнопки статусов/раундов/отказа, разбор колбэков.

callback_data ≤64 байта (лимит Telegram): формат `crm:<action>[:<arg>]:<vacancy_id>`.
Кнопки строятся из статуса и уже пройденных раундов — движок переходов остаётся
в домене (§3.3): бот лишь предлагает допустимые действия, домен валидирует.
"""

from __future__ import annotations

from typing import NamedTuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pydantic import BaseModel, ConfigDict

from app.domain.crm import ApplicationStatus, InterviewRoundKind, RejectStage

_NO_ARG = {"save", "del", "iv"}
_WITH_ARG = {"adv", "rnd", "rej"}

# Допустимые этапы отказа по статусу (§3.3) — для кнопок; домен всё равно валидирует.
_REJECT_STAGES: dict[str, list[RejectStage]] = {
    "new": [RejectStage.PRE_HR, RejectStage.HR],
    "applied": [RejectStage.PRE_HR, RejectStage.HR],
    "interview": [RejectStage.HR, RejectStage.TECH, RejectStage.FINAL],
}

_STATUS_RU = {
    "new": "новая",
    "applied": "отклик отправлен",
    "interview": "собеседования",
    "offer": "оффер 🎉",
    "rejected": "отказ",
}


class CrmCallback(NamedTuple):
    """Разобранный CRM-колбэк: действие, необязательный аргумент, id вакансии."""

    action: str
    arg: str | None
    vacancy_id: int


class SavedApplicationView(BaseModel):
    """UI-модель заявки для `/saved` (не доменная сущность)."""

    model_config = ConfigDict(frozen=True)

    vacancy_id: int
    title: str
    company: str
    status: str
    rounds: list[str]
    interview_url: str | None = None
    notes: str | None = None


def parse_crm_callback(data: str) -> CrmCallback:
    """`crm:adv:applied:7` → CrmCallback('adv','applied',7); мусор → ValueError."""
    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "crm":
        raise ValueError(f"не crm-callback: {data!r}")
    action = parts[1]
    if action in _NO_ARG and len(parts) == 3:
        return CrmCallback(action=action, arg=None, vacancy_id=int(parts[2]))
    if action in _WITH_ARG and len(parts) == 4:
        return CrmCallback(action=action, arg=parts[2], vacancy_id=int(parts[3]))
    raise ValueError(f"неизвестный crm-action/формат: {data!r}")


def build_save_button(vacancy_id: int) -> InlineKeyboardButton:
    """💾 Сохранить на карточке дайджеста → создаёт Application(new) ([C-U4])."""
    return InlineKeyboardButton(text="💾 Сохранить", callback_data=f"crm:save:{vacancy_id}")


def _next_rounds(rounds: list[str]) -> list[InterviewRoundKind]:
    """Раунды с рангом строго выше последнего пройденного (C2)."""
    last_rank = max(
        (InterviewRoundKind.rank(InterviewRoundKind(k)) for k in rounds),
        default=-1,
    )
    return [k for k in InterviewRoundKind if InterviewRoundKind.rank(k) > last_rank]


def build_saved_keyboard(view: SavedApplicationView) -> InlineKeyboardMarkup:
    """Контекстные кнопки по статусу заявки (§3.3): только допустимые следующие шаги."""
    vid = view.vacancy_id
    rows: list[list[InlineKeyboardButton]] = []

    if view.status == ApplicationStatus.NEW:
        rows.append(
            [InlineKeyboardButton(text="📨 Откликнулся", callback_data=f"crm:adv:applied:{vid}")]
        )
    elif view.status == ApplicationStatus.APPLIED:
        rows.append(
            [InlineKeyboardButton(text="🎤 На собес", callback_data=f"crm:adv:interview:{vid}")]
        )
    elif view.status == ApplicationStatus.INTERVIEW:
        round_btns = [
            InlineKeyboardButton(text=f"➕ {k.value}", callback_data=f"crm:rnd:{k.value}:{vid}")
            for k in _next_rounds(view.rounds)
        ]
        for i in range(0, len(round_btns), 3):
            rows.append(round_btns[i : i + 3])
        rows.append(
            [
                InlineKeyboardButton(text="🎉 Оффер", callback_data=f"crm:adv:offer:{vid}"),
                InlineKeyboardButton(text="➕ собес", callback_data=f"crm:iv:{vid}"),
            ]
        )

    reject_stages = _REJECT_STAGES.get(view.status)
    if reject_stages:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"❌ {stage.value}", callback_data=f"crm:rej:{stage.value}:{vid}"
                )
                for stage in reject_stages
            ]
        )

    rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"crm:del:{vid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_saved_text(view: SavedApplicationView) -> str:
    """Текст заявки: заголовок, статус, раунды, собес-детали."""
    lines = [
        f"{view.title} — {view.company}",
        f"Статус: {_STATUS_RU.get(view.status, view.status)}",
    ]
    if view.rounds:
        lines.append("Раунды: " + " → ".join(view.rounds))
    if view.interview_url:
        lines.append(f"Ссылка: {view.interview_url}")
    if view.notes:
        lines.append(f"Заметки: {view.notes}")
    return "\n".join(lines)
