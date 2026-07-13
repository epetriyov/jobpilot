"""Контекст CORRESPONDENCE: входящие письма (DOMAIN.md §3.4)."""

from app.domain.correspondence.inbox import (
    InboxMessage,
    MailVerdict,
    PrefilterDecision,
    prefilter,
)

__all__ = ["InboxMessage", "MailVerdict", "PrefilterDecision", "prefilter"]
