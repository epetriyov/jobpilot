"""Use case BuildInviteBatch (спека 003, US1): еженедельный пакет заготовок.

[N-C1] декартово произведение companies×roles минус активные пары;
[N-U2]/N2 — текст через LlmPort (реджект → retry в адаптере → шаблонный фолбэк);
N1 — только ссылка и текст, никакого LinkedIn-трафика.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from opentelemetry import trace

from app.domain.networking import InviteDraft, InviteText, people_search_url
from app.domain.shared import PromptVersion
from app.obs.metrics import invite_drafts_total
from app.ports.llm import LlmPort
from app.ports.networking import InviteRepositoryPort
from app.ports.notifier import InviteCard, NotifierPort

log = structlog.get_logger("application.build_invite_batch")
tracer = trace.get_tracer("jobpilot.application")

FALLBACK_TEMPLATE = (
    "Здравствуйте! Я Engineering Manager (10+ лет: платформы, финтех). "
    "Слежу за {company} — интересно, как устроена инженерная культура. "
    "Буду рад связаться и обменяться опытом."
)


@dataclass
class InviteBatchResult:
    created: int
    pending_reminder: int


class BuildInviteBatch:
    def __init__(
        self,
        *,
        repo: InviteRepositoryPort,
        llm: LlmPort,
        notifier: NotifierPort,
        system_prompt: str,
        prompt_version: PromptVersion,
        companies: list[str],
        roles: list[str],
        remind_days: int,
        dry_run: bool,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._notifier = notifier
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version
        self._companies = companies
        self._roles = roles
        self._remind_days = remind_days
        self._dry_run = dry_run

    async def run(self) -> InviteBatchResult:
        from app.domain.networking import build_pairs

        if not self._companies:
            await self._notifier.send_message(
                "🤝 Нетворкинг: список компаний пуст — добавьте LINKEDIN_COMPANIES в .env."
            )
            return InviteBatchResult(created=0, pending_reminder=await self._remind())

        with tracer.start_as_current_span("invites.build") as span:
            active = await self._repo.active_pairs()
            pairs = build_pairs(companies=self._companies, roles=self._roles, active=active)
            span.set_attribute("invites.pairs", len(pairs))

            mark = "🧪 ТЕСТ " if self._dry_run else ""
            if not pairs:
                await self._notifier.send_message(
                    f"{mark}🤝 Новых заготовок нет — все пары активны."
                )
            else:
                await self._notifier.send_message(f"{mark}🤝 Пакет инвайтов: {len(pairs)}")

            created = 0
            for company, role in pairs:
                draft = await self._make_draft(company=company, role=role)
                invite_id = await self._repo.add(draft)
                await self._notifier.send_invite_card(
                    InviteCard(
                        invite_id=invite_id,
                        title=draft.title,
                        company=draft.company,
                        search_url=draft.search_url,
                        invite_text=draft.invite_text,
                        status=draft.status,
                    )
                )
                invite_drafts_total.add(1, {"status": "proposed"})
                created += 1

        pending = await self._remind()
        log.info("invite_batch_done", created=created, pending_reminder=pending)
        return InviteBatchResult(created=created, pending_reminder=pending)

    async def _make_draft(self, *, company: str, role: str) -> InviteDraft:
        verdict = await self._llm.complete(
            purpose="invite",
            prompt_version=self._prompt_version,
            system=self._system_prompt,
            data=f"Роль адресата: {role}\nКомпания: {company}",
            response_model=InviteText,
        )
        text = verdict.text if verdict else FALLBACK_TEMPLATE.format(company=company)[:300]
        return InviteDraft(
            title=role,
            company=company,
            search_url=people_search_url(role=role, company=company),
            invite_text=text,
        )

    async def _remind(self) -> int:
        pending = await self._repo.pending_older_than(self._remind_days)
        if pending:
            await self._notifier.send_message(
                f"⏰ Неотправленных инвайтов: {len(pending)} — посмотреть: /invites_pending"
            )
        return len(pending)
