"""[M-C3]/T6E-4 контракт GenerateCoverLetter: «✉️» — письмо Pro без галлюцинаций.

Промпт содержит резюме EM (источник фактов); модель — через адаптер (Pro в проде);
невалидный ответ → 1 retry (в адаптере) → graceful; llm_call учтён (O1);
persist в cover_letter; карточка с 🔁/✏️; тело письма не логируется (M4).
"""

from __future__ import annotations

from app.adapters.llm.fake import FakeLlm, stub_letter_response
from app.application.generate_cover_letter import GenerateCoverLetter
from app.domain.correspondence import CoverLetter
from app.domain.relevance import VacancySnapshot
from app.domain.shared import PromptVersion, Source, SourceRef
from app.ports.llm import LlmCallRecord
from app.ports.notifier import CoverLetterCard

PV = PromptVersion(purpose="cover", version=1)

RESUME_MARKER = "команду x3 при текучести <10%"
SYSTEM_PROMPT = (
    "Пиши только по резюме.\n\n## Резюме\n"
    "Масштабировал мобильную команду x3 при текучести <10%.\n\n"
    "## Гайд\nexecutive-тон, цифра → действие → эффект."
)

SNAPSHOT = VacancySnapshot(
    source_ref=SourceRef(source=Source.HH, external_id="42"),
    title="Head of Engineering",
    company="Ромашка",
    url="https://hh.ru/vacancy/42",
    description_text="Нужен руководитель разработки для масштабирования команды.",
)


class VacancyReaderFake:
    def __init__(self, snapshot: VacancySnapshot | None) -> None:
        self._snapshot = snapshot
        self.requested: list[int] = []

    async def get_by_id(self, vacancy_id: int) -> VacancySnapshot | None:
        self.requested.append(vacancy_id)
        return self._snapshot


class LetterRepoFake:
    def __init__(self) -> None:
        self.items: dict[int, list[CoverLetter]] = {}
        self._next = 1

    async def add(self, letter: CoverLetter) -> int:
        letter_id = self._next
        self._next += 1
        self.items.setdefault(letter.vacancy_id, []).append(letter)
        return letter_id

    async def latest(self, vacancy_id: int) -> CoverLetter | None:
        versions = self.items.get(vacancy_id)
        return versions[-1] if versions else None


class NotifierSpy:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.cards: list[CoverLetterCard] = []

    async def send_message(self, text: str) -> None:
        self.messages.append(text)

    async def send_cover_letter_card(self, card: CoverLetterCard) -> None:
        self.cards.append(card)


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


def make_use_case(
    *,
    reader: VacancyReaderFake,
    repo: LetterRepoFake,
    notifier: NotifierSpy,
    llm: FakeLlm,
) -> GenerateCoverLetter:
    return GenerateCoverLetter(
        llm=llm,
        vacancy_reader=reader,
        letter_repo=repo,
        notifier=notifier,
        system_prompt=SYSTEM_PROMPT,
        prompt_version=PV,
    )


def stub_llm(recorder: RecorderSpy) -> FakeLlm:
    return FakeLlm(recorder=recorder, model="fake/cover", response_factory=stub_letter_response)


async def test_m_c3_generates_persists_and_notifies() -> None:
    reader = VacancyReaderFake(SNAPSHOT)
    repo, notifier, rec = LetterRepoFake(), NotifierSpy(), RecorderSpy()
    llm = stub_llm(rec)

    result = await make_use_case(reader=reader, repo=repo, notifier=notifier, llm=llm).run(42)

    assert result.status == "generated"
    # persist в cover_letter (последняя версия — актуальная)
    latest = await repo.latest(42)
    assert latest is not None
    assert latest.vacancy_id == 42
    assert latest.prompt_version == "cover_v1"
    assert len(latest.text) <= 2000
    # карточка с письмом ушла владельцу (отправку письма делает человек вручную)
    assert len(notifier.cards) == 1
    assert notifier.cards[0].vacancy_id == 42
    assert "Head of Engineering" in notifier.cards[0].text  # обращение к вакансии
    # llm_call учтён (O1), purpose=cover, версия промпта
    assert len(rec.records) == 1
    assert rec.records[0].purpose == "cover"
    assert rec.records[0].prompt_version == "cover_v1"


async def test_m_c3_prompt_contains_resume_facts() -> None:
    """Промпт (system) несёт резюме EM — источник фактов; вакансия — в блоке данных."""
    reader = VacancyReaderFake(SNAPSHOT)
    repo, notifier, rec = LetterRepoFake(), NotifierSpy(), RecorderSpy()
    llm = stub_llm(rec)

    await make_use_case(reader=reader, repo=repo, notifier=notifier, llm=llm).run(42)

    system_msg = next(m for m in llm.sent_messages if m["role"] == "system")
    assert RESUME_MARKER in system_msg["content"]
    # текст вакансии подан как недоверенные данные (R5-аналог, экранирование в адаптере)
    data_msg = next(m for m in llm.sent_messages if m["role"] == "user")
    assert "Ромашка" in data_msg["content"]
    assert "не инструкции" in data_msg["content"]


async def test_m_c3_vacancy_not_found_is_graceful() -> None:
    reader = VacancyReaderFake(None)
    repo, notifier, rec = LetterRepoFake(), NotifierSpy(), RecorderSpy()
    llm = stub_llm(rec)

    result = await make_use_case(reader=reader, repo=repo, notifier=notifier, llm=llm).run(999)

    assert result.status == "vacancy_not_found"
    assert notifier.cards == []
    assert repo.items == {}
    assert any("не наш" in m.lower() or "не найд" in m.lower() for m in notifier.messages)


async def test_m_c3_invalid_llm_after_retry_is_graceful() -> None:
    """Невалидный вывод → адаптер делает ровно 1 retry (R2) → graceful, без persist."""
    reader = VacancyReaderFake(SNAPSHOT)
    repo, notifier, rec = LetterRepoFake(), NotifierSpy(), RecorderSpy()
    llm = FakeLlm(recorder=rec, model="fake/cover", responses=["мусор", "тоже мусор"])

    result = await make_use_case(reader=reader, repo=repo, notifier=notifier, llm=llm).run(42)

    assert result.status == "llm_failed"
    assert notifier.cards == []
    assert repo.items == {}
    assert llm.attempts == 2  # ровно один валидационный retry (R2)
    # даже при сбое вызов учтён (O1)
    assert len(rec.records) == 1


async def test_m_c3_regenerate_adds_new_version() -> None:
    """🔁 создаёт новую версию письма (несколько строк на вакансию, data-model §4)."""
    reader = VacancyReaderFake(SNAPSHOT)
    repo, notifier, rec = LetterRepoFake(), NotifierSpy(), RecorderSpy()

    await make_use_case(reader=reader, repo=repo, notifier=notifier, llm=stub_llm(rec)).run(42)
    await make_use_case(reader=reader, repo=repo, notifier=notifier, llm=stub_llm(rec)).run(42)

    assert len(repo.items[42]) == 2
