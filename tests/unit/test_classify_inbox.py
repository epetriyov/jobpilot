"""Use case ClassifyInbox: [M-C1] только 24ч + дедуп; M1 префильтр; M2 фолбэк;
[M-U3] маршрутизация LinkedIn; O1 llm_call. На фейках.
"""

from datetime import UTC, datetime, timedelta

from app.adapters.llm.fake import FakeLlm, stub_mail_response
from app.application.classify_inbox import ClassifyInbox
from app.domain.correspondence import InboxMessage
from app.domain.shared import PromptVersion
from app.ports.inbox import RawEmail

NOW = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)
SINCE = NOW - timedelta(hours=24)
PV = PromptVersion(purpose="mail_classify", version=1)


def email(
    gmail_id: str,
    sender: str = "recruiter@bigtech.io",
    subject: str = "Позиция Engineering Manager",
    body: str = "Приглашаем на интервью на позицию EM.",
    age_hours: int = 2,
) -> RawEmail:
    return RawEmail(
        gmail_id=gmail_id,
        sender=sender,
        subject=subject,
        snippet=body[:100],
        body_text=body,
        received_at=NOW - timedelta(hours=age_hours),
        url=f"https://mail.google.com/mail/u/0/#inbox/{gmail_id}",
    )


class InboxFake:
    def __init__(self, emails: list[RawEmail]) -> None:
        self._emails = emails

    async def fetch_since(self, since: datetime) -> list[RawEmail]:
        return [e for e in self._emails if e.received_at >= since]


class RepoFake:
    def __init__(self) -> None:
        self.saved: dict[str, InboxMessage] = {}

    async def is_processed(self, gmail_id: str) -> bool:
        return gmail_id in self.saved

    async def add(self, gmail_id: str, message: InboxMessage) -> None:
        self.saved[gmail_id] = message


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def record(self, call: object) -> None:
        self.records.append(call)


def make_use_case(inbox: InboxFake, repo: RepoFake, llm: FakeLlm) -> ClassifyInbox:
    return ClassifyInbox(
        inbox=inbox,
        repo=repo,
        llm=llm,
        system_prompt="Классифицируй письмо.",
        prompt_version=PV,
        body_limit=2000,
    )


def stub_llm(recorder: RecorderSpy | None = None) -> FakeLlm:
    return FakeLlm(
        recorder=recorder or RecorderSpy(),
        model="fake/mail-stub",
        response_factory=stub_mail_response,
    )


async def test_m_c1_only_last_24h_and_dedup() -> None:
    """[M-C1] 3 свежих + 1 старое → обработаны ровно 3; повторный прогон не дублирует."""
    emails = [email("m1"), email("m2"), email("m3"), email("old", age_hours=30)]
    repo = RepoFake()
    use_case = make_use_case(InboxFake(emails), repo, stub_llm())

    await use_case.run(since=SINCE)
    assert set(repo.saved) == {"m1", "m2", "m3"}

    await use_case.run(since=SINCE)  # идемпотентность
    assert len(repo.saved) == 3


async def test_m1_newsletter_dropped_without_llm_and_not_persisted() -> None:
    recorder = RecorderSpy()
    llm = stub_llm(recorder)
    repo = RepoFake()
    emails = [email("promo", sender="promo@shop.ru", subject="Скидки! unsubscribe")]

    await make_use_case(InboxFake(emails), repo, llm).run(since=SINCE)

    assert repo.saved == {}
    assert llm.attempts == 0  # LLM не вызывался (M1)


async def test_m_u3_linkedin_routed_without_llm() -> None:
    llm = stub_llm()
    repo = RepoFake()
    emails = [email("li1", sender="invitations@linkedin.com", subject="Ivan wants to connect")]

    await make_use_case(InboxFake(emails), repo, llm).run(since=SINCE)

    saved = repo.saved["li1"]
    assert saved.source == "linkedin_gmail"
    assert saved.section == "linkedin"
    assert llm.attempts == 0


async def test_hh_notification_hidden() -> None:
    repo = RepoFake()
    emails = [email("hh1", sender="noreply@hh.ru", subject="Новый отклик")]
    await make_use_case(InboxFake(emails), repo, stub_llm()).run(since=SINCE)
    assert repo.saved["hh1"].section == "hidden"


async def test_job_email_classified_with_summary_and_llm_call() -> None:
    recorder = RecorderSpy()
    repo = RepoFake()
    await make_use_case(InboxFake([email("j1")]), repo, stub_llm(recorder)).run(since=SINCE)

    saved = repo.saved["j1"]
    assert saved.section == "mail"
    assert saved.summary  # summary от классификатора
    assert len(recorder.records) == 1  # O1


async def test_not_job_persisted_hidden() -> None:
    repo = RepoFake()
    emails = [email("n1", sender="friend@gmail.com", subject="Шашлыки в субботу", body="Приходи!")]
    await make_use_case(InboxFake(emails), repo, stub_llm()).run(since=SINCE)
    assert repo.saved["n1"].section == "hidden"  # персист для дедупа, в секции не идёт


async def test_m2_invalid_llm_output_falls_back_to_unclassified_mail() -> None:
    """Невалидный выход дважды → письмо НЕ теряется: секция mail, summary=None
    (принцип «ноль пропусков офферов» [M-E1])."""
    repo = RepoFake()
    llm = FakeLlm(recorder=RecorderSpy(), responses=["мусор", "тоже мусор"])

    await make_use_case(InboxFake([email("f1")]), repo, llm).run(since=SINCE)

    saved = repo.saved["f1"]
    assert saved.section == "mail"
    assert saved.summary is None
