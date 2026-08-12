"""Рендер аналитики в Telegram (этап 6C): /stats, /costs и карточка /review.

Чистые функции форматирования: домен/use case отдают отчёты, здесь — текст и
клавиатуры. Вердикт модели в карточке ревью скрыт, чтобы не смещать оценку владельца.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.funnel_stats import FunnelReport
from app.application.report_costs import CostReport
from app.application.review_agreement import ReviewCandidate, ReviewSummary
from app.domain.relevance import Verdict

_STATUS_RU = {
    "new": "новые",
    "applied": "отклик отправлен",
    "interview": "собеседования",
    "offer": "офферы 🎉",
    "rejected": "отказы",
}


def _pct(rate: float) -> str:
    return f"{rate * 100:.0f}%"


def _num(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render_funnel(report: FunnelReport) -> str:
    """Текст /stats: воронка по статусам, конверсии вперёд, счётчики хранилища/разметки."""
    lines = [f"📊 Воронка заявок (всего {report.total}):"]
    for status, ru in _STATUS_RU.items():
        lines.append(f"• {ru}: {report.counts.get(status, 0)}")
    lines.append("")
    lines.append("Конверсии (вперёд):")
    lines.append(f"• → отклик: {_pct(report.applied_rate)}")
    lines.append(f"• отклик → собес: {_pct(report.interview_rate)}")
    lines.append(f"• собес → оффер: {_pct(report.offer_rate)}")
    lines.append("")
    lines.append(f"Вакансий в базе: {report.vacancies_total} (скоренных {report.vacancies_scored})")
    lines.append(f"Разметка: 👍 {report.labeled_relevant} / 👎 {report.labeled_irrelevant}")
    return "\n".join(lines)


def render_costs(report: CostReport) -> str:
    """Текст /costs: суммарные $ и токены за период + разбивка по назначению."""
    t = report.totals
    lines = [
        f"💸 Затраты LLM за {report.days} дн.:",
        f"Итого: ${t.total_usd:.4f} ({t.calls} вызовов)",
        f"Токены: {_num(t.input_tokens + t.output_tokens)} "
        f"(вход {_num(t.input_tokens)} / выход {_num(t.output_tokens)})",
    ]
    if t.by_purpose:
        lines.append("По назначению:")
        for purpose, cost in sorted(t.by_purpose.items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"• {purpose}: ${cost:.4f}")
    return "\n".join(lines)


def parse_review_callback(data: str) -> Verdict:
    """`rev:up` → 'relevant', `rev:down` → 'irrelevant'; мусор → ValueError."""
    mapping: dict[str, Verdict] = {"rev:up": "relevant", "rev:down": "irrelevant"}
    if data not in mapping:
        raise ValueError(f"не review-callback: {data!r}")
    return mapping[data]


def build_review_keyboard() -> InlineKeyboardMarkup:
    """Кнопки вердикта владельца на карточке ревью (👍 релевантна / 👎 нет)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 подходит", callback_data="rev:up"),
                InlineKeyboardButton(text="👎 нет", callback_data="rev:down"),
            ]
        ]
    )


def render_review_candidate(cand: ReviewCandidate, index: int, total: int) -> str:
    """Карточка вакансии на ревью: заголовок, скор, ссылка (без вердикта модели)."""
    return "\n".join(
        [
            f"🔎 Ревью {index + 1}/{total}",
            f"{cand.title} — {cand.company}",
            f"⭐ скор {cand.score}/100",
            cand.url,
            "",
            "Подходит эта вакансия?",
        ]
    )


def render_review_summary(summary: ReviewSummary) -> str:
    """Финальная сводка ревью: agreement rate владельца против скора модели."""
    return "\n".join(
        [
            "✅ Ревью завершено.",
            f"Согласие со скором: {_pct(summary.agreement_rate)} "
            f"({summary.agreed}/{summary.total})",
            f"Расхождения записаны в разметку: {summary.disagreed}",
        ]
    )
