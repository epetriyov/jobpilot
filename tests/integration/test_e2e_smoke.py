"""[X-I1] E2E smoke в DRY_RUN: полный пайплайн на фикстурах → дайджест, каждый шаг = OTel span."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.application.smoke_pipeline import RunSmokePipeline
from app.worker.fixtures import sample_hh


class SpyNotifier:
    def __init__(self) -> None:
        self.digests: list[str] = []

    async def send_digest(self, text: str) -> None:
        self.digests.append(text)

    async def send_message(self, text: str) -> None:  # pragma: no cover
        ...


class NullPublisher:
    async def publish(self) -> None:  # pragma: no cover
        ...


async def test_full_dry_run_pipeline_emits_step_spans(span_exporter: InMemorySpanExporter) -> None:
    notifier = SpyNotifier()
    pipeline = RunSmokePipeline(
        notifier=notifier,
        publisher=NullPublisher(),
        dry_run=True,
        sources={"hh": sample_hh},
    )

    result = await pipeline.run()

    assert result.dry_run is True
    assert notifier.digests and "ТЕСТ" in notifier.digests[0]

    span_names = {s.name for s in span_exporter.get_finished_spans()}
    assert {"smoke.collect", "smoke.dedup", "smoke.publish", "smoke.notify"} <= span_names
