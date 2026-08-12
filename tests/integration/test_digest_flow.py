"""[T110] RunDailyDigest: сбор → seen(снапшот) → скоринг → отбор → карточки → sent.

[F-I2] DRY_RUN помечает дайджест «ТЕСТ»; S1/S2 — без повторов и дублей;
S4 — падение источника даёт partial; R1 — повторный прогон не дёргает LLM.
Реальные Postgres-репозитории (testcontainers), фейковые источник/LLM/нотификатор.
"""

from __future__ import annotations

import pytest

from app.adapters.llm.fake import FakeLlm
from app.adapters.persistence.repositories import SeenVacancyRepository
from app.application.run_daily_digest import RunDailyDigest
from app.application.score_vacancy import ScoreVacancy
from app.domain.shared import PromptVersion, Salary, Source, SourceRef
from app.domain.sourcing import Vacancy
from app.ports.llm import LlmCallRecord
from app.ports.notifier import DigestCard

pytestmark = pytest.mark.integration

PV = PromptVersion(purpose="scoring", version=1)
VALID = '{"score": 77, "reason": "матч"}'


def vacancy(
    i: str,
    *,
    source: Source = Source.HH,
    site: str | None = None,
    title: str = "Engineering Manager",
    company: str = "Acme",
) -> Vacancy:
    return Vacancy.create(
        source_ref=SourceRef(source=source, site_name=site, external_id=i),
        title=title,
        company=f"{company} {i}" if company == "Acme" else company,
        url=f"https://hh.ru/vacancy/{i}",
        description_raw=f"<p>Команда {i}</p>",
        salary=Salary(from_=300_000, currency="RUR"),
    )


class FakeSource:
    def __init__(self, name: str, items: list[Vacancy]) -> None:
        self.name = name
        self._items = items

    async def fetch(self) -> list[Vacancy]:
        return self._items


class FailingSource:
    name = "broken"

    async def fetch(self) -> list[Vacancy]:
        raise RuntimeError("boom")


class SpyNotifier:
    def __init__(self) -> None:
        self.digests: list[str] = []
        self.cards: list[DigestCard] = []

    async def send_digest(self, text: str) -> None:
        self.digests.append(text)

    async def send_message(self, text: str) -> None: ...

    async def send_card(self, card: DigestCard) -> None:
        self.cards.append(card)


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


class EmptyLabels:
    async def recent(self, limit: int = 10) -> list:  # type: ignore[type-arg]
        return []


def make_pipeline(db_session, sources, notifier, llm, *, dry_run=True):  # type: ignore[no-untyped-def]
    seen = SeenVacancyRepository(db_session)
    scorer = ScoreVacancy(
        llm=llm,
        seen_repo=seen,
        label_repo=EmptyLabels(),
        system_prompt="Оцени вакансию для EM.",
        prompt_version=PV,
        model_name="fake/model",
    )
    return RunDailyDigest(
        sources=sources,
        seen_repo=seen,
        scorer=scorer,
        notifier=notifier,
        dry_run=dry_run,
        threshold=60,
        max_items=50,
    )


async def test_full_flow_dry_run(db_session) -> None:  # type: ignore[no-untyped-def]
    notifier = SpyNotifier()
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID] * 10)
    sources = [FakeSource("hh", [vacancy("1"), vacancy("2")]), FailingSource()]

    result = await make_pipeline(db_session, sources, notifier, llm).run()
    await db_session.commit()

    assert result.partial is True  # S4: сломанный источник не уронил прогон
    assert result.discovered == 2
    assert len(notifier.cards) == 2
    card = notifier.cards[0]
    assert card.score == 77 and card.reason == "матч"
    assert "300" in (card.salary_text or "")
    assert notifier.digests and "ТЕСТ" in notifier.digests[0]  # [F-I2]


async def test_second_run_no_repeats_and_no_llm_calls(db_session) -> None:  # type: ignore[no-untyped-def]
    """S1 (без повторов в дайджесте) + R1 (LLM не вызывается повторно)."""
    notifier = SpyNotifier()
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID] * 10)
    sources = [FakeSource("hh", [vacancy("1"), vacancy("2")])]

    await make_pipeline(db_session, sources, notifier, llm).run()
    await db_session.commit()
    attempts_after_first = llm.attempts

    notifier2 = SpyNotifier()
    await make_pipeline(db_session, sources, notifier2, llm).run()
    await db_session.commit()

    assert attempts_after_first == 2
    assert llm.attempts == attempts_after_first  # R1: повторного скоринга нет
    assert notifier2.cards == []  # повторных карточек нет


async def test_cross_source_duplicate_not_in_digest(db_session) -> None:  # type: ignore[no-untyped-def]
    """S2: та же (company, title) из другого источника за 30 дней — не в дайджест."""
    notifier = SpyNotifier()
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID] * 10)
    original = vacancy("10", company="Globex")
    dup = vacancy("999", source=Source.SITE, site="vk", company="Globex")

    await make_pipeline(db_session, [FakeSource("hh", [original])], notifier, llm).run()
    await db_session.commit()

    notifier2 = SpyNotifier()
    await make_pipeline(db_session, [FakeSource("vk", [dup])], notifier2, llm).run()
    await db_session.commit()

    assert notifier2.cards == []


async def test_x_i1_each_stage_is_span(db_session, span_exporter) -> None:  # type: ignore[no-untyped-def]
    """[X-I1] Каждый шаг дайджеста — отдельный OTel child span."""
    notifier = SpyNotifier()
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID] * 5)
    await make_pipeline(db_session, [FakeSource("hh", [vacancy("span1")])], notifier, llm).run()
    await db_session.commit()

    names = {span.name for span in span_exporter.get_finished_spans()}
    assert {
        "digest.collect",
        "digest.dedup",
        "digest.scoring",
        "digest.select",
        "digest.notify",
    } <= names


async def test_below_threshold_not_sent(db_session) -> None:  # type: ignore[no-untyped-def]
    notifier = SpyNotifier()
    llm = FakeLlm(recorder=RecorderSpy(), responses=['{"score": 20, "reason": "не матч"}'])

    result = await make_pipeline(
        db_session, [FakeSource("hh", [vacancy("low1")])], notifier, llm
    ).run()
    await db_session.commit()

    assert result.discovered == 1
    assert notifier.cards == []  # заскорено, но ниже порога 60
    # источник ОТДАЛ вакансию → это «новых нет», НЕ health-алерт (без ложной тревоги)
    assert "⚠️" not in notifier.digests[0]
    assert "нет" in notifier.digests[0].lower()


async def test_sources_empty_warns_owner(db_session) -> None:  # type: ignore[no-untyped-def]
    """#5: реальные источники вернули 0 сырья → видимый владельцу ⚠️ (сбой доступа),
    а не молчаливое «новых нет» (иначе мёртвый токен/смена формата тонут незаметно)."""
    notifier = SpyNotifier()
    llm = FakeLlm(recorder=RecorderSpy(), responses=[VALID] * 3)

    result = await make_pipeline(db_session, [FakeSource("hh", [])], notifier, llm).run()
    await db_session.commit()

    assert result.discovered == 0
    assert notifier.cards == []
    assert notifier.digests and "⚠️" in notifier.digests[0]
    assert "0 вакансий" in notifier.digests[0]
