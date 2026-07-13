"""Services — фабрика сценариев этапа 1 с session-per-operation.

HH-источник подключается сюда после получения кредов владельца (T107):
без них список источников пуст — дайджест честно отвечает «новых нет».
"""

from __future__ import annotations

from pathlib import Path

import structlog
from aiogram import Bot

from app.adapters.hh.fake import FakeHhVacancySource
from app.adapters.llm.fake import FakeLlm, stub_scoring_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.adapters.persistence.database import make_engine, make_session_factory
from app.adapters.persistence.dataset import JsonlDatasetAppender
from app.adapters.persistence.repositories import (
    JobRunRepository,
    LabelRepository,
    LlmCallRepository,
    SeenVacancyRepository,
)
from app.adapters.telegram.notifier import NullPublisher, TelegramNotifier
from app.application.job_runner import run_job
from app.application.label_vacancy import LabelVacancy
from app.application.publish_resume import PublishResult, PublishResume
from app.application.run_daily_digest import DigestResult, RunDailyDigest
from app.application.score_vacancy import ScoreVacancy
from app.config import Settings
from app.domain.relevance import LabeledVacancy, Verdict
from app.domain.shared import PromptVersion
from app.ports.sources import VacancySourcePort

log = structlog.get_logger("runtime.composition")

SCORING_PROMPT_VERSION = PromptVersion(purpose="scoring", version=1)
RELEVANCE_DATASET = Path("eval/datasets/relevance/v1.jsonl")
PROFILE_PATH = Path("resumes/resume_em.md")
PROFILE_LIMIT = 4000


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
        # один инстанс на процесс: счётчик fetch'ей даёт «новые» вакансии на повторный /digest
        self._fake_hh = FakeHhVacancySource()
        log.info(
            "services_ready",
            hh_mode=settings.resolved_hh_mode(),
            llm_mode=settings.resolved_llm_mode(),
            dry_run=settings.dry_run,
        )

    def _sources(self) -> list[VacancySourcePort]:
        if self._settings.resolved_hh_mode() == "fake":
            return [self._fake_hh]
        if not self._settings.hh_refresh_token:
            log.warning("hh_source_disabled", reason="HH_MODE=real, но нет HH-кредов")
            return []
        # T107: HhVacancySource подключается после записи golden-файлов
        return []

    def _llm(self, session: object):  # type: ignore[no-untyped-def]
        recorder = LlmCallRepository(session)  # type: ignore[arg-type]
        if self._settings.resolved_llm_mode() == "fake":
            # стаб-скоринг: детерминированные скоры, честный llm_call (O1)
            return FakeLlm(
                recorder=recorder,
                model="fake/scoring-stub",
                response_factory=stub_scoring_response,
            )
        return InstructorOpenRouterLlm(settings=self._settings, recorder=recorder)

    async def run_digest(self) -> DigestResult:
        async with self._factory() as session:
            seen = SeenVacancyRepository(session)
            scorer = ScoreVacancy(
                llm=self._llm(session),
                seen_repo=seen,
                label_repo=LabelRepository(session),
                system_prompt=self._system_prompt,
                prompt_version=SCORING_PROMPT_VERSION,
                model_name=(
                    "fake/scoring-stub"
                    if self._settings.resolved_llm_mode() == "fake"
                    else self._settings.llm_model_scoring
                ),
                fewshot_limit=self._settings.fewshot_limit,
                fewshot_text_limit=self._settings.fewshot_text_limit,
            )
            digest = RunDailyDigest(
                sources=self._sources(),
                seen_repo=seen,
                scorer=scorer,
                notifier=TelegramNotifier(self._bot, self._settings.owner_chat_id),
                dry_run=self._settings.dry_run,
                threshold=self._settings.digest_score_threshold,
                max_items=self._settings.digest_max_items,
            )
            result = await digest.run()
            await session.commit()
            return result

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
            )
            labeled = await use_case.label(ref_key, verdict)
            await session.commit()
            return labeled

    async def train_progress(self) -> tuple[int, int]:
        async with self._factory() as session:
            return await LabelRepository(session).counts()

    async def publish(self) -> PublishResult:
        # NullPublisher до T115 (адаптер HH publish появится с golden 429)
        use_case = PublishResume(publisher=NullPublisher(), dry_run=self._settings.dry_run)
        return await use_case.run()

    async def publish_as_job(self) -> None:
        async with self._factory() as session:
            repo = JobRunRepository(session)

            async def job(ctx: dict) -> tuple[int, int]:  # type: ignore[type-arg]
                result = await self.publish()
                return (1, 1 if result.status == "published" else 0)

            await run_job("publish_resume", repo, job)
            await session.commit()
