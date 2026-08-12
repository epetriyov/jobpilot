"""Контекст CORRESPONDENCE: входящие письма (DOMAIN.md §3.4) + сопроводительные (6E)."""

from app.domain.correspondence.hr import HR_GIST_MAX_CHARS, HrDetails
from app.domain.correspondence.inbox import (
    InboxMessage,
    MailVerdict,
    PrefilterDecision,
    prefilter,
)
from app.domain.correspondence.letter import (
    COVER_LETTER_MAX_CHARS,
    CoverLetter,
    CoverLetterOut,
)

__all__ = [
    "COVER_LETTER_MAX_CHARS",
    "HR_GIST_MAX_CHARS",
    "CoverLetter",
    "CoverLetterOut",
    "HrDetails",
    "InboxMessage",
    "MailVerdict",
    "PrefilterDecision",
    "prefilter",
]
