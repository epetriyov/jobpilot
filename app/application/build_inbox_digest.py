"""Use case BuildInboxDigest (спека 002): секции «Почта» и «LinkedIn» в дайджест.

Сбой сбора почты изолируется вызывающей стороной (S4-паттерн): секции —
дополнение к дайджесту вакансий, а не его условие.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import structlog
from opentelemetry import trace

from app.application.classify_inbox import ClassifyInbox
from app.domain.correspondence import InboxMessage
from app.ports.notifier import NotifierPort

log = structlog.get_logger("application.build_inbox_digest")
tracer = trace.get_tracer("jobpilot.application")


class SectionsRepoPort(Protocol):
    async def sections_since(self, since: datetime) -> dict[str, list[InboxMessage]]: ...


class BuildInboxDigest:
    def __init__(
        self,
        *,
        classify: ClassifyInbox,
        sections_repo: SectionsRepoPort,
        notifier: NotifierPort,
    ) -> None:
        self._classify = classify
        self._sections_repo = sections_repo
        self._notifier = notifier

    async def run(self, since: datetime) -> dict[str, int]:
        with tracer.start_as_current_span("inbox.classify"):
            counts = await self._classify.run(since)

        with tracer.start_as_current_span("inbox.render"):
            sections = await self._sections_repo.sections_since(since)
            text = render_sections(sections)
            if text:
                await self._notifier.send_message(text)

        return counts


def render_sections(sections: dict[str, list[InboxMessage]]) -> str | None:
    """Пустые секции скрываются (спека 002, edge case)."""
    blocks: list[str] = []

    mail = sections.get("mail", [])
    if mail:
        lines = [f"📬 Почта ({len(mail)})"]
        for m in mail:
            summary = m.summary or f"(не классифицировано) {m.subject}"
            lines.append(f"• {m.sender}: {summary}\n  {m.url}")
        blocks.append("\n".join(lines))

    linkedin = sections.get("linkedin", [])
    if linkedin:
        lines = [f"💼 LinkedIn ({len(linkedin)})"]
        lines += [f"• {m.subject}\n  {m.url}" for m in linkedin]
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else None
