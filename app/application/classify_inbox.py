"""Use case ClassifyInbox (спека 002, US1): письма за 24ч → секции дайджеста.

M1 — эвристический префильтр до LLM; M2 — summary по схеме, невалидно →
1 retry → unclassified-фолбэк (письмо не теряется — «ноль пропусков офферов»);
M4 — тела/темы писем не логируются: только gmail_id, домен и счётчики.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import structlog

from app.domain.correspondence import InboxMessage, MailVerdict, prefilter
from app.domain.shared import PromptVersion
from app.obs.metrics import inbox_messages_total
from app.ports.inbox import InboxMessageRepositoryPort, InboxPort, RawEmail
from app.ports.llm import LlmPort

log = structlog.get_logger("application.classify_inbox")


class ClassifyInbox:
    def __init__(
        self,
        *,
        inbox: InboxPort,
        repo: InboxMessageRepositoryPort,
        llm: LlmPort,
        system_prompt: str,
        prompt_version: PromptVersion,
        body_limit: int,
        extra_whitelist: tuple[str, ...] = (),
    ) -> None:
        self._inbox = inbox
        self._repo = repo
        self._llm = llm
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version
        self._body_limit = body_limit
        self._extra_whitelist = extra_whitelist

    async def run(self, since: datetime) -> dict[str, int]:
        emails = [e for e in await self._inbox.fetch_since(since) if e.received_at >= since]
        counts = {"mail": 0, "linkedin": 0, "hidden": 0, "dropped": 0}

        for raw in emails:
            if await self._repo.is_processed(raw.gmail_id):
                continue
            message = await self._classify(raw)
            if message is None:
                counts["dropped"] += 1
                continue
            await self._repo.add(raw.gmail_id, message)
            counts[message.section] += 1
            inbox_messages_total.add(1, {"section": message.section})

        # M4: только счётчики — ни тем, ни тел
        log.info("inbox_classified", since=since.isoformat(), **counts)
        return counts

    async def _classify(self, raw: RawEmail) -> InboxMessage | None:
        decision = prefilter(
            sender=raw.sender, subject=raw.subject, extra_whitelist=self._extra_whitelist
        )
        if decision == "drop":
            return None
        if decision == "linkedin":
            return self._message(raw, source="linkedin_gmail", section="linkedin", summary=None)
        if decision == "hidden":
            return self._message(raw, source="hh", section="hidden", summary=None)

        verdict = await self._llm.complete(
            purpose="summary",
            prompt_version=self._prompt_version,
            system=self._system_prompt,
            data=(
                f"From: {raw.sender}\nSubject: {raw.subject}\n\n{raw.body_text[: self._body_limit]}"
            ),
            response_model=MailVerdict,
        )
        if verdict is None:
            # R2/M2-фолбэк: показываем письмо с темой — пропуск оффера хуже шума
            log.warning("mail_unclassified", gmail_id=raw.gmail_id)
            return self._message(raw, source="gmail", section="mail", summary=None)
        if not verdict.is_job:
            return self._message(raw, source="gmail", section="hidden", summary=None)
        return self._message(raw, source="gmail", section="mail", summary=verdict.summary)

    @staticmethod
    def _message(
        raw: RawEmail,
        *,
        source: Literal["gmail", "linkedin_gmail", "hh"],
        section: Literal["mail", "linkedin", "hidden"],
        summary: str | None,
    ) -> InboxMessage:
        return InboxMessage(
            source=source,
            sender=raw.sender,
            subject=raw.subject,
            summary=summary,
            url=raw.url,
            received_at=raw.received_at,
            section=section,
        )
