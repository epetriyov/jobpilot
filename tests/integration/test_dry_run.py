"""[F-I2] DRY_RUN=true → внешних записей нет (publish не вызван), дайджест помечен «ТЕСТ»."""

from app.application.smoke_pipeline import RunSmokePipeline
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy


class SpyNotifier:
    def __init__(self) -> None:
        self.digests: list[str] = []
        self.messages: list[str] = []

    async def send_digest(self, text: str) -> None:
        self.digests.append(text)

    async def send_message(self, text: str) -> None:
        self.messages.append(text)


class SpyPublisher:
    def __init__(self) -> None:
        self.calls = 0

    async def publish(self) -> None:
        self.calls += 1


def _fixture_vacancy(i: str) -> Vacancy:
    return Vacancy.create(
        source_ref=SourceRef(source=Source.HH, external_id=i),
        title="Engineering Manager",
        company=f"Company {i}",
        url=f"https://hh.ru/{i}",
        description_raw="<p>Ведём команду</p>",
    )


async def test_dry_run_marks_digest_and_skips_publish() -> None:
    notifier = SpyNotifier()
    publisher = SpyPublisher()
    pipeline = RunSmokePipeline(
        notifier=notifier,
        publisher=publisher,
        dry_run=True,
        sources={"hh": lambda: [_fixture_vacancy("1"), _fixture_vacancy("2")]},
    )

    result = await pipeline.run()

    assert publisher.calls == 0  # внешняя запись не произведена
    assert len(notifier.digests) == 1
    assert "ТЕСТ" in notifier.digests[0]
    assert result.dry_run is True
    assert result.digest_items == 2


async def test_live_mode_allows_publish() -> None:
    notifier = SpyNotifier()
    publisher = SpyPublisher()
    pipeline = RunSmokePipeline(
        notifier=notifier,
        publisher=publisher,
        dry_run=False,
        sources={"hh": lambda: [_fixture_vacancy("1")]},
    )

    await pipeline.run()

    assert publisher.calls == 1
    assert "ТЕСТ" not in notifier.digests[0]
