"""[T116] PublishResume: DRY_RUN не вызывает источник ([F-I2]);
лимит — штатный исход, не ошибка ([S-C3]-механика на уровне use case).
"""

from app.application.publish_resume import PublishResume
from app.ports.notifier import PublishOutcome


class PublisherSpy:
    def __init__(self, outcome: PublishOutcome = "published") -> None:
        self.calls = 0
        self._outcome = outcome

    async def publish(self) -> PublishOutcome:
        self.calls += 1
        return self._outcome


async def test_dry_run_never_calls_publisher() -> None:
    publisher = PublisherSpy()

    result = await PublishResume(publisher=publisher, dry_run=True).run()

    assert publisher.calls == 0
    assert result.status == "dry_run"


async def test_published() -> None:
    publisher = PublisherSpy("published")

    result = await PublishResume(publisher=publisher, dry_run=False).run()

    assert publisher.calls == 1
    assert result.status == "published"


async def test_limit_is_normal_outcome_not_error() -> None:
    publisher = PublisherSpy("skipped_limit")

    result = await PublishResume(publisher=publisher, dry_run=False).run()

    assert result.status == "skipped_limit"  # без исключений — job останется success


async def test_disabled_is_not_reported_as_published() -> None:
    # заглушка без рабочего канала → "disabled", не ложный "published" (метрика не врёт)
    publisher = PublisherSpy("disabled")

    result = await PublishResume(publisher=publisher, dry_run=False).run()

    assert result.status == "disabled"
