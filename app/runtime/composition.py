"""Services — фабрика сценариев этапа 1 с session-per-operation.

HH-источник подключается сюда после получения кредов владельца (T107):
без них список источников пуст — дайджест честно отвечает «новых нет».
"""

from __future__ import annotations

from pathlib import Path

import structlog
from aiogram import Bot

from app.adapters.embeddings.fake import FakeEmbedder
from app.adapters.embeddings.openrouter import OpenRouterEmbedder
from app.adapters.getmatch.fake import FakeGetMatchSource
from app.adapters.getmatch.source import GetMatchApiClient, GetMatchSource
from app.adapters.gmail.fake import FakeGmailInbox
from app.adapters.gmail.source import GmailInbox
from app.adapters.hh.fake import FakeHhVacancySource
from app.adapters.llm.fake import (
    FakeLlm,
    stub_invite_response,
    stub_mail_response,
    stub_scoring_response,
)
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.adapters.persistence.database import make_engine, make_session_factory
from app.adapters.persistence.dataset import JsonlDatasetAppender
from app.adapters.persistence.repositories import (
    ApplicationRepository,
    InboxMessageRepository,
    InviteRepository,
    JobRunRepository,
    LabelRepository,
    LlmCallRepository,
    ScraperApprovalRepository,
    SeenVacancyRepository,
    VacancyRepository,
)
from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.registry import SITE_ADAPTERS, SiteFactory
from app.adapters.telegram.crm_cards import SavedApplicationView
from app.adapters.telegram.notifier import NullPublisher, TelegramNotifier
from app.application.add_interview_details import AddInterviewDetails
from app.application.add_interview_details import Outcome as DetailsOutcome
from app.application.backfill_embeddings import BackfillEmbeddings
from app.application.build_inbox_digest import BuildInboxDigest
from app.application.build_invite_batch import BuildInviteBatch, InviteBatchResult
from app.application.change_status import ChangeApplicationStatus
from app.application.change_status import Outcome as ChangeOutcome
from app.application.classify_inbox import ClassifyInbox
from app.application.fewshot import FewShotSelectorPort, SemanticSelector
from app.application.job_runner import run_job
from app.application.label_vacancy import LabelVacancy
from app.application.publish_resume import PublishResult, PublishResume
from app.application.run_daily_digest import DigestResult, RunDailyDigest
from app.application.save_vacancy import Outcome as SaveOutcome
from app.application.save_vacancy import SaveVacancy
from app.application.score_vacancy import ScoreVacancy
from app.application.update_invite_status import Outcome as InviteOutcome
from app.application.update_invite_status import UpdateInviteStatus
from app.config import Settings
from app.domain.crm import ApplicationStatus, InterviewRoundKind, RejectStage
from app.domain.relevance import LabeledVacancy, Verdict
from app.domain.shared import PromptVersion
from app.ports.embeddings import EmbeddingPort
from app.ports.inbox import InboxPort
from app.ports.notifier import PublisherPort
from app.ports.sources import VacancySourcePort
from app.runtime.approval import ApprovalOutcome, available_scrapers, is_known_site

log = structlog.get_logger("runtime.composition")

SCORING_PROMPT_VERSION = PromptVersion(purpose="scoring", version=1)
MAIL_PROMPT_VERSION = PromptVersion(purpose="mail_classify", version=1)
INVITE_PROMPT_VERSION = PromptVersion(purpose="invite", version=2)
RELEVANCE_DATASET = Path("eval/datasets/relevance/v1.jsonl")
PROFILE_PATH = Path("resumes/resume_em.md")
PROFILE_LIMIT = 4000


def build_site_sources(
    settings: Settings,
    *,
    escalate: EscalateFn | None = None,
    registry: dict[str, SiteFactory] | None = None,
) -> list[SiteAdapter]:
    """Собрать адаптеры сайтов по конфигу (SITES_ACTIVE ∪ SITES_CANARY).

    Незарегистрированный (ещё не реализованный) сайт — пропуск с предупреждением,
    не роняет остальные (S4). Реестр пуст в фундаменте (off-by-default).
    """
    reg = SITE_ADAPTERS if registry is None else registry
    sources: list[SiteAdapter] = []
    seen: set[str] = set()
    for site in [*settings.sites_active, *settings.sites_canary]:
        if site in seen:
            continue
        seen.add(site)
        factory = reg.get(site)
        if factory is None:
            log.warning("site_adapter_not_registered", site=site)
            continue
        sources.append(factory(settings, escalate))
    return sources


def build_getmatch_sources(
    settings: Settings,
    *,
    escalate: EscalateFn | None = None,
) -> list[VacancySourcePort]:
    """Источник GetMatch по флагу (этап 4, off-by-default, constitution VI).

    `getmatch` не в SOURCES → пусто (выключен по умолчанию). Включён + fake →
    детерминированный стаб (сеть не трогается). Включён + real → GetMatchSource
    поверх httpx-клиента `/api/offers` (1 rps, честный UA, robots `Disallow:/api/`
    — осознанное owner-решение, см. source.py). Падение изолируется коллектором (S4).
    """
    if "getmatch" not in settings.sources:
        return []
    if settings.resolved_getmatch_mode() == "fake":
        return [FakeGetMatchSource()]
    client = GetMatchApiClient(
        api_url=settings.getmatch_api_url,
        user_agent=settings.getmatch_user_agent,
        pause_sec=settings.getmatch_request_pause_sec,
        timeout_sec=settings.getmatch_timeout_sec,
    )
    return [
        GetMatchSource(
            client=client,
            page_limit=settings.getmatch_page_limit,
            escalate=escalate,
        )
    ]


def _system_prompt() -> str:
    prompt = load_system_prompt("scoring", SCORING_PROMPT_VERSION.version)
    if PROFILE_PATH.exists():
        profile = PROFILE_PATH.read_text(encoding="utf-8")[:PROFILE_LIMIT]
        return f"{prompt}\n\n## Профиль кандидата (резюме)\n{profile}"
    log.warning("profile_missing", path=str(PROFILE_PATH))
    return prompt


class Services:
    """Собирает use cases; каждый вызов — своя сессия БД (commit по завершении)."""

    def __init__(self, settings: Settings, bot: Bot) -> None:
        self._settings = settings
        self._bot = bot
        self._engine = make_engine(settings.postgres_dsn.get_secret_value())
        self._factory = make_session_factory(self._engine)
        self._system_prompt = _system_prompt()
        # один инстанс на процесс: счётчики fetch'ей дают «новые» элементы на повторный /digest
        self._fake_hh = FakeHhVacancySource()
        self._fake_gmail = FakeGmailInbox()
        log.info(
            "services_ready",
            hh_mode=settings.resolved_hh_mode(),
            gmail_mode=settings.resolved_gmail_mode(),
            llm_mode=settings.resolved_llm_mode(),
            dry_run=settings.dry_run,
        )

    def _sources(self) -> list[VacancySourcePort]:
        if self._settings.resolved_hh_mode() == "fake":
            return [self._fake_hh]
        # Реальные источники по HH_SOURCES (пересмотр 2026-07-15). Падение любого
        # изолируется в RunDailyDigest (S4): собранное из остальных не теряется.
        s = self._settings
        sources: list[VacancySourcePort] = []
        if "email" in s.hh_sources and s.gmail_refresh_token and s.gmail_client_id:
            # HH шлёт «Вакансии по подписке» на почту → парсим из Gmail (этап 2)
            from app.adapters.gmail.source import GmailInbox
            from app.adapters.hh.email_source import HhEmailSource

            inbox = GmailInbox(
                client_id=s.gmail_client_id,
                client_secret=s.gmail_client_secret.get_secret_value(),  # type: ignore[union-attr]
                refresh_token=s.gmail_refresh_token.get_secret_value(),
            )
            sources.append(HhEmailSource(inbox=inbox, since_hours=s.hh_email_since_hours))
        if "telegram" in s.hh_sources and s.hh_userbot_api_id and s.hh_userbot_api_hash:
            from app.adapters.hh.telegram_source import HhTelegramSource
            from app.adapters.telegram_userbot.reader import TelethonReader

            reader = TelethonReader(
                api_id=s.hh_userbot_api_id,
                api_hash=s.hh_userbot_api_hash.get_secret_value(),
                session_path=s.hh_userbot_session,
            )
            sources.append(HhTelegramSource(reader=reader, bot_username=s.hh_bot_username))
        if "web" in s.hh_sources:
            from app.adapters.hh.web_playwright import PlaywrightLoader
            from app.adapters.hh.web_source import HhWebSource

            loader = PlaywrightLoader(
                profile_dir=s.hh_web_profile_dir,
                user_agent=s.hh_user_agent,
                pause_sec=s.hh_request_pause_sec,
            )
            sources.append(HhWebSource(page_loader=loader, url=s.hh_recommendations_url))
        if not sources:
            log.warning("hh_no_real_sources", sources=s.hh_sources)
        return sources

    def _site_sources(self) -> list[SiteAdapter]:
        """Активные + canary сайты-скрейперы (этап 5). Реестр пуст до по-сайтовых задач."""

        async def escalate(text: str) -> None:
            await TelegramNotifier(self._bot, self._settings.owner_chat_id).send_message(text)

        return build_site_sources(self._settings, escalate=escalate)

    def _getmatch_sources(self) -> list[VacancySourcePort]:
        """Источник GetMatch по флагу SOURCES (этап 4, off-by-default). Падение — S4."""

        async def escalate(text: str) -> None:
            await TelegramNotifier(self._bot, self._settings.owner_chat_id).send_message(text)

        return build_getmatch_sources(self._settings, escalate=escalate)

    async def approve_scraper(self, site: str) -> tuple[ApprovalOutcome, list[str]]:
        """US3: одобрить сайт-скрейпер. Неизвестный → отказ + список доступных."""
        if not is_known_site(site):
            available = available_scrapers(
                canary=self._settings.sites_canary, active=self._settings.sites_active
            )
            return "unknown", available
        async with self._factory() as session:
            repo = ScraperApprovalRepository(session)
            if await repo.is_approved(site):
                return "already", []
            await repo.approve(site, self._settings.owner_chat_id)
            await session.commit()
            log.info("scraper_approved", site=site)
            return "approved", []

    def _llm(self, session: object, *, kind: str = "scoring"):  # type: ignore[no-untyped-def]
        recorder = LlmCallRepository(session)  # type: ignore[arg-type]
        if self._settings.resolved_llm_mode() == "fake":
            # детерминированные стабы per-purpose, честный llm_call (O1)
            factories = {
                "scoring": stub_scoring_response,
                "mail_classify": stub_mail_response,
                "invite": stub_invite_response,
            }
            factory = factories.get(kind, stub_scoring_response)
            return FakeLlm(recorder=recorder, model=f"fake/{kind}-stub", response_factory=factory)
        return InstructorOpenRouterLlm(settings=self._settings, recorder=recorder)

    def _embedder(self, session: object) -> EmbeddingPort:
        """EmbeddingPort (этап 6D): fake-стаб без ключей, иначе OpenRouter. Учёт O1."""
        recorder = LlmCallRepository(session)  # type: ignore[arg-type]
        if self._settings.resolved_llm_mode() == "fake":
            return FakeEmbedder(recorder=recorder)
        return OpenRouterEmbedder(settings=self._settings, recorder=recorder)

    def _scoring_selector(
        self, session: object, label_repo: LabelRepository
    ) -> FewShotSelectorPort | None:
        """Стратегия few-shot по конфигу (FEWSHOT_SELECTOR): semantic ∥ None→recent-дефолт."""
        if self._settings.fewshot_selector != "semantic":
            return None  # ScoreVacancy сам построит RecentSelector (дефолт, R3)
        return SemanticSelector(
            label_repo,
            embedder=self._embedder(session),
            limit=self._settings.fewshot_limit,
            text_limit=self._settings.fewshot_text_limit,
            min_embedded=self._settings.fewshot_min_embedded,
        )

    async def run_digest(self) -> DigestResult:
        async with self._factory() as session:
            seen = SeenVacancyRepository(session)
            label_repo = LabelRepository(session)
            scorer = ScoreVacancy(
                llm=self._llm(session),
                seen_repo=seen,
                label_repo=label_repo,
                system_prompt=self._system_prompt,
                prompt_version=SCORING_PROMPT_VERSION,
                model_name=(
                    "fake/scoring-stub"
                    if self._settings.resolved_llm_mode() == "fake"
                    else self._settings.llm_model_scoring
                ),
                fewshot_limit=self._settings.fewshot_limit,
                fewshot_text_limit=self._settings.fewshot_text_limit,
                selector=self._scoring_selector(session, label_repo),
            )
            sources: list[VacancySourcePort] = list(self._sources())
            sources += self._getmatch_sources()
            sources += self._site_sources()
            digest = RunDailyDigest(
                sources=sources,
                seen_repo=seen,
                scorer=scorer,
                notifier=TelegramNotifier(self._bot, self._settings.owner_chat_id),
                dry_run=self._settings.dry_run,
                threshold=self._settings.digest_score_threshold,
                max_items=self._settings.digest_max_items,
                canary_sites=set(self._settings.sites_canary),
                approval=ScraperApprovalRepository(session),
            )
            result = await digest.run()

            # Секции «Почта»/«LinkedIn» (этап 2): сбой изолируется — вакансии уже ушли
            try:
                await self._run_inbox_sections(session)
            except Exception as exc:
                log.warning("inbox_sections_failed", error=str(exc))
                result.partial = True

            await session.commit()
            return result

    async def _run_inbox_sections(self, session: object) -> None:
        from datetime import UTC, datetime, timedelta

        inbox = self._inbox()
        if inbox is None:
            return
        classify = ClassifyInbox(
            inbox=inbox,
            repo=InboxMessageRepository(session),  # type: ignore[arg-type]
            llm=self._llm(session, kind="mail_classify"),
            system_prompt=load_system_prompt("mail_classify", MAIL_PROMPT_VERSION.version),
            prompt_version=MAIL_PROMPT_VERSION,
            body_limit=self._settings.mail_body_limit,
            extra_whitelist=self._settings.mail_whitelist_domains,
        )
        use_case = BuildInboxDigest(
            classify=classify,
            sections_repo=InboxMessageRepository(session),  # type: ignore[arg-type]
            notifier=TelegramNotifier(self._bot, self._settings.owner_chat_id),
        )
        await use_case.run(since=datetime.now(UTC) - timedelta(hours=24))

    def _inbox(self) -> InboxPort | None:
        if self._settings.resolved_gmail_mode() == "fake":
            return self._fake_gmail
        s = self._settings
        if not (s.gmail_client_id and s.gmail_client_secret and s.gmail_refresh_token):
            log.warning("gmail_source_disabled", reason="GMAIL_MODE=real, но креды неполные")
            return None
        return GmailInbox(
            client_id=s.gmail_client_id,
            client_secret=s.gmail_client_secret.get_secret_value(),
            refresh_token=s.gmail_refresh_token.get_secret_value(),
        )

    async def build_invites(self) -> InviteBatchResult:
        async with self._factory() as session:
            use_case = BuildInviteBatch(
                repo=InviteRepository(session),
                llm=self._llm(session, kind="invite"),
                notifier=TelegramNotifier(self._bot, self._settings.owner_chat_id),
                system_prompt=load_system_prompt("invite", INVITE_PROMPT_VERSION.version),
                prompt_version=INVITE_PROMPT_VERSION,
                companies=self._settings.linkedin_companies,
                roles=self._settings.linkedin_roles,
                remind_days=self._settings.invites_remind_days,
                dry_run=self._settings.dry_run,
            )
            result = await use_case.run()
            await session.commit()
            return result

    async def build_invites_as_job(self) -> None:
        async with self._factory() as session:
            repo = JobRunRepository(session)

            async def job(ctx: dict) -> tuple[int, int]:  # type: ignore[type-arg]
                result = await self.build_invites()
                return result.created, result.created

            await run_job("weekly_invites", repo, job)
            await session.commit()

    async def update_invite(self, invite_id: int, action: str) -> InviteOutcome:
        from app.domain.networking import InviteStatus

        async with self._factory() as session:
            use_case = UpdateInviteStatus(repo=InviteRepository(session))
            outcome = await use_case.run(invite_id, InviteStatus(action))
            await session.commit()
            return outcome

    async def invites_pending(self) -> list[str]:
        async with self._factory() as session:
            pending = await InviteRepository(session).pending()
            return [f"{d.title} @ {d.company}\n{d.search_url}" for _, d in pending]

    async def invites_counts(self) -> dict[str, int]:
        async with self._factory() as session:
            return await InviteRepository(session).counts()

    async def run_digest_as_job(self) -> None:
        """Плановый запуск: JobRun + root span + trace_id в логах."""
        async with self._factory() as session:
            repo = JobRunRepository(session)

            async def job(ctx: dict) -> tuple[int, int]:  # type: ignore[type-arg]
                result = await self.run_digest()
                ctx["partial"] = result.partial
                return result.discovered, result.cards_sent

            await run_job("daily_digest", repo, job)
            await session.commit()

    async def label(self, ref_key: str, verdict: Verdict) -> LabeledVacancy | None:
        async with self._factory() as session:
            use_case = LabelVacancy(
                seen_repo=SeenVacancyRepository(session),
                label_repo=LabelRepository(session),
                dataset=JsonlDatasetAppender(RELEVANCE_DATASET),
                embedder=self._embedder(session),  # 6D: эмбеддинг при разметке (иначе backfill)
            )
            labeled = await use_case.label(ref_key, verdict)
            await session.commit()
            return labeled

    async def backfill_embeddings(self, batch_limit: int = 200) -> int:
        """6D: идемпотентно наполнить эмбеддинги исторических размеченных (ops/джоб)."""
        async with self._factory() as session:
            use_case = BackfillEmbeddings(
                label_repo=LabelRepository(session), embedder=self._embedder(session)
            )
            done = await use_case.run(batch_limit)
            await session.commit()
            return done

    async def train_progress(self) -> tuple[int, int]:
        async with self._factory() as session:
            return await LabelRepository(session).counts()

    # --- CRM (этап 6B): 💾 Сохранить, /saved, статусы/раунды/отказ, 🗑, ➕ собес ---

    async def save_vacancy(self, vacancy_id: int) -> SaveOutcome:
        async with self._factory() as session:
            use_case = SaveVacancy(
                apps=ApplicationRepository(session),
                vacancies=VacancyRepository(session),
            )
            outcome, _ = await use_case.run(vacancy_id)
            await session.commit()
            return outcome

    async def advance_application(self, vacancy_id: int, to: ApplicationStatus) -> ChangeOutcome:
        async with self._factory() as session:
            outcome = await ChangeApplicationStatus(apps=ApplicationRepository(session)).advance(
                vacancy_id, to
            )
            await session.commit()
            return outcome

    async def add_application_round(
        self, vacancy_id: int, kind: InterviewRoundKind
    ) -> ChangeOutcome:
        async with self._factory() as session:
            outcome = await ChangeApplicationStatus(apps=ApplicationRepository(session)).add_round(
                vacancy_id, kind
            )
            await session.commit()
            return outcome

    async def reject_application(self, vacancy_id: int, stage: RejectStage | None) -> ChangeOutcome:
        async with self._factory() as session:
            outcome = await ChangeApplicationStatus(apps=ApplicationRepository(session)).reject(
                vacancy_id, stage
            )
            await session.commit()
            return outcome

    async def delete_application(self, vacancy_id: int) -> ChangeOutcome:
        async with self._factory() as session:
            outcome = await ChangeApplicationStatus(apps=ApplicationRepository(session)).delete(
                vacancy_id
            )
            await session.commit()
            return outcome

    async def add_interview_details(
        self, vacancy_id: int, *, url: str | None = None, notes: str | None = None
    ) -> DetailsOutcome:
        async with self._factory() as session:
            outcome = await AddInterviewDetails(apps=ApplicationRepository(session)).run(
                vacancy_id, url=url, notes=notes
            )
            await session.commit()
            return outcome

    async def saved_applications(self) -> list[SavedApplicationView]:
        async with self._factory() as session:
            apps = ApplicationRepository(session)
            vacancies = VacancyRepository(session)
            views: list[SavedApplicationView] = []
            for app in await apps.list_all():
                vacancy = await vacancies.get_by_id(app.vacancy_id)
                views.append(
                    SavedApplicationView(
                        vacancy_id=app.vacancy_id,
                        title=vacancy.title if vacancy else "—",
                        company=vacancy.company if vacancy else "—",
                        status=str(app.status),
                        rounds=[str(r.kind) for r in app.interview_rounds],
                        interview_url=app.interview_url,
                        notes=app.notes,
                    )
                )
            return views

    async def publish(self) -> PublishResult:
        use_case = PublishResume(publisher=self._publisher(), dry_run=self._settings.dry_run)
        return await use_case.run()

    def _publisher(self) -> PublisherPort:
        s = self._settings
        # real-режим + web-источник + URL резюме → Playwright-клик; иначе заглушка
        if s.resolved_hh_mode() == "real" and "web" in s.hh_sources and s.hh_resume_url:
            from app.adapters.hh.resume_playwright import PlaywrightResumeActor
            from app.adapters.hh.web_publish import HhWebPublisher

            actor = PlaywrightResumeActor(
                profile_dir=s.hh_web_profile_dir, user_agent=s.hh_user_agent
            )
            return HhWebPublisher(actor=actor, resume_url=s.hh_resume_url)
        return NullPublisher()

    async def publish_as_job(self) -> None:
        async with self._factory() as session:
            repo = JobRunRepository(session)

            async def job(ctx: dict) -> tuple[int, int]:  # type: ignore[type-arg]
                result = await self.publish()
                return (1, 1 if result.status == "published" else 0)

            await run_job("publish_resume", repo, job)
            await session.commit()
