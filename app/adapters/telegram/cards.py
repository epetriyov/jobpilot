"""Карточка вакансии в Telegram: текст + клавиатура 👍/👎/🔗 (T111/T113).

callback_data ≤64 байта (лимит Telegram) — формат `label:<verdict>:<ref_key>`.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.relevance import Verdict
from app.ports.notifier import DigestCard


def build_card_keyboard(card: DigestCard) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍", callback_data=f"label:relevant:{card.ref_key}"),
                InlineKeyboardButton(text="👎", callback_data=f"label:irrelevant:{card.ref_key}"),
                InlineKeyboardButton(text="🔗", url=card.url),
            ]
        ]
    )


def render_card_text(card: DigestCard) -> str:
    lines = [f"<b>{card.title}</b> — {card.company}"]
    if card.salary_text:
        lines.append(f"💰 {card.salary_text}")
    lines.append(f"⭐ {card.score}/100 — {card.reason}")
    return "\n".join(lines)


def parse_label_callback(data: str) -> tuple[Verdict, str]:
    """`label:relevant:hh:42` → ("relevant", "hh:42"); мусор → ValueError."""
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[0] != "label" or parts[1] not in ("relevant", "irrelevant"):
        raise ValueError(f"не label-callback: {data!r}")
    verdict: Verdict = parts[1]  # type: ignore[assignment]
    return verdict, parts[2]
