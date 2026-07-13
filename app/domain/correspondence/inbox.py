"""Правила обработки входящих писем (DOMAIN.md §3.4: M1, M2; кейсы M-U1..M-U3).

Чистый домен: эвристика префильтра и схемы — без I/O.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PrefilterDecision = Literal["llm", "linkedin", "hidden", "drop"]

# M1: whitelist-домены — кандидаты «про работу» (LLM подтверждает и делает summary)
WHITELIST_DOMAINS = ("getmatch.ru", "habr.com", "career.habr.com")

# hh.ru: рабочее письмо, но переписка HH уже показывается секцией negotiations (этап 1)
HH_DOMAINS = ("hh.ru",)

LINKEDIN_DOMAINS = ("linkedin.com",)
_LINKEDIN_SUBJECT_MARKERS = ("wants to connect", "invitation", "new message", "messaged you")

# маркеры рассылок/промо: отсев до LLM (экономия токенов, M1)
_NEWSLETTER_MARKERS = ("unsubscribe", "скидк", "распродаж", "промокод", "успейте купить")


def _domain(sender: str) -> str:
    return sender.rsplit("@", 1)[-1].lower().strip(">")


def prefilter(
    *, sender: str, subject: str, extra_whitelist: tuple[str, ...] = ()
) -> PrefilterDecision:
    """M1: эвристика до LLM.

    linkedin → секция LinkedIn без LLM ([M-U3]); hh → hidden (покрыто negotiations);
    whitelist → LLM; явные рассылки → drop ([M-U1]); прочее → LLM
    (неизвестный рекрутёр важнее экономии — «ноль пропусков офферов», [M-E1]).
    """
    domain = _domain(sender)
    lowered_subject = subject.lower()

    if any(domain.endswith(d) for d in LINKEDIN_DOMAINS):
        if any(marker in lowered_subject for marker in _LINKEDIN_SUBJECT_MARKERS):
            return "linkedin"
        return "llm"  # нетипичное письмо LinkedIn — пусть решает классификатор

    if any(domain.endswith(d) for d in HH_DOMAINS):
        return "hidden"

    if any(domain.endswith(d) for d in (*WHITELIST_DOMAINS, *extra_whitelist)):
        return "llm"

    haystack = f"{sender.lower()} {lowered_subject}"
    if any(marker in haystack for marker in _NEWSLETTER_MARKERS):
        return "drop"

    return "llm"


class MailVerdict(BaseModel):
    """Схема выхода LLM-классификации (M2): summary ≤200 знаков и ≤2 строк."""

    is_job: bool
    summary: str = Field(max_length=200)

    @field_validator("summary")
    @classmethod
    def _max_two_lines(cls, value: str) -> str:
        if value.count("\n") > 1:
            raise ValueError("summary должен быть не длиннее 2 строк (M2)")
        return value


class InboxMessage(BaseModel):
    """Входящее письмо о работе (DOMAIN.md §1) — метаданные + summary, без тела (M4)."""

    model_config = ConfigDict(frozen=True)

    source: Literal["gmail", "linkedin_gmail", "hh"]
    sender: str
    subject: str
    summary: str | None
    url: str
    received_at: datetime
    section: Literal["mail", "linkedin", "hidden"]
