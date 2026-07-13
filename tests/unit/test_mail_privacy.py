"""[M-C2] Тело письма отсутствует в логах при обработке (инвариант M4)."""

import io
import logging
from datetime import UTC, datetime, timedelta

import structlog

from app.adapters.llm.fake import FakeLlm, stub_mail_response
from app.application.classify_inbox import ClassifyInbox
from app.domain.shared import PromptVersion
from app.obs.logging import configure_logging
from app.ports.inbox import RawEmail

BODY_MARKER = "СЕКРЕТНОЕ-ТЕЛО-ПИСЬМА-ac1f"
SUBJECT_MARKER = "ТЕМА-ПИСЬМА-b7e2"


class _Repo:
    def __init__(self) -> None:
        self.saved: dict[str, object] = {}

    async def is_processed(self, gmail_id: str) -> bool:
        return False

    async def add(self, gmail_id: str, message: object) -> None:
        self.saved[gmail_id] = message


class _Recorder:
    async def record(self, call: object) -> None: ...


class _Inbox:
    async def fetch_since(self, since: datetime) -> list[RawEmail]:
        return [
            RawEmail(
                gmail_id="p1",
                sender="recruiter@bigtech.io",
                subject=f"Интервью {SUBJECT_MARKER}",
                snippet=BODY_MARKER[:20],
                body_text=f"Здравствуйте! {BODY_MARKER}. Приглашаем на интервью.",
                received_at=datetime.now(UTC),
                url="https://mail.google.com/#inbox/p1",
            )
        ]


async def test_email_body_never_logged() -> None:
    stream = io.StringIO()
    configure_logging(secret_values=[], stream=stream)
    try:
        use_case = ClassifyInbox(
            inbox=_Inbox(),
            repo=_Repo(),
            llm=FakeLlm(recorder=_Recorder(), response_factory=stub_mail_response),
            system_prompt="Классифицируй.",
            prompt_version=PromptVersion(purpose="mail_classify", version=1),
            body_limit=2000,
        )
        await use_case.run(since=datetime.now(UTC) - timedelta(hours=24))
    finally:
        logs = stream.getvalue()
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()

    assert logs, "прогон должен что-то логировать"
    assert BODY_MARKER not in logs  # тело письма — никогда (M4)
    assert SUBJECT_MARKER not in logs  # и тему не пишем: минимум метаданных
