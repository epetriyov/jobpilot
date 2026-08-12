"""Карточка вакансии в Telegram: текст + клавиатура 👍/👎/🔗 (T111/T113).

callback_data ≤64 байта (лимит Telegram) — формат `label:<verdict>:<ref_key>`.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.adapters.telegram.crm_cards import build_save_button
from app.domain.relevance import Verdict
from app.ports.notifier import DigestCard, InviteCard


def build_card_keyboard(card: DigestCard) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="👍", callback_data=f"label:relevant:{card.ref_key}"),
            InlineKeyboardButton(text="👎", callback_data=f"label:irrelevant:{card.ref_key}"),
            InlineKeyboardButton(text="🔗", url=card.url),
        ]
    ]
    # 💾 Сохранить в CRM — только когда известен id вакансии (этап 6B; см. DigestCard).
    if card.vacancy_id is not None:
        rows.append([build_save_button(card.vacancy_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_card_text(card: DigestCard) -> str:
    lines = [f"<b>{card.title}</b> — {card.company}"]
    if card.salary_text:
        lines.append(f"💰 {card.salary_text}")
    lines.append(f"⭐ {card.score}/100 — {card.reason}")
    if card.note:  # пометка источника site:<name> (· canary) — этап 5
        lines.append(f"🔖 {card.note}")
    return "\n".join(lines)


def parse_label_callback(data: str) -> tuple[Verdict, str]:
    """`label:relevant:hh:42` → ("relevant", "hh:42"); мусор → ValueError."""
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[0] != "label" or parts[1] not in ("relevant", "irrelevant"):
        raise ValueError(f"не label-callback: {data!r}")
    verdict: Verdict = parts[1]  # type: ignore[assignment]
    return verdict, parts[2]


def build_invite_keyboard(card: InviteCard) -> InlineKeyboardMarkup:
    """Кнопки по статусу: proposed → «Отправил»; sent → «Принял»; accepted — только ссылка."""
    buttons = []
    if card.status == "proposed":
        buttons.append(
            InlineKeyboardButton(text="📤 Отправил", callback_data=f"inv:sent:{card.invite_id}")
        )
    elif card.status == "sent":
        buttons.append(
            InlineKeyboardButton(text="✅ Принял", callback_data=f"inv:accepted:{card.invite_id}")
        )
    buttons.append(InlineKeyboardButton(text="🔎 Поиск людей", url=card.search_url))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def render_invite_text(card: InviteCard) -> str:
    status_ru = {"proposed": "к отправке", "sent": "отправлен", "accepted": "принят ✅"}
    return (
        f"<b>{card.title}</b> @ {card.company} · {status_ru.get(card.status, card.status)}\n"
        f"<code>{card.invite_text}</code>"
    )


def parse_invite_callback(data: str) -> tuple[str, int]:
    """`inv:sent:7` → ("sent", 7); мусор → ValueError."""
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[0] != "inv" or parts[1] not in ("sent", "accepted"):
        raise ValueError(f"не invite-callback: {data!r}")
    return parts[1], int(parts[2])
