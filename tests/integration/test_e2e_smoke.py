"""[X-I1] E2E smoke в DRY_RUN: полный пайплайн на фикстурах → дайджест, каждый шаг = OTel span."""

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.application.smoke_pipeline import RunSmokePipeline
from app.obs.tracing import setup_tracing
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


@pytest.fixture()
def spans() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = setup_tracing(service_name="e2e-smoke", exporter=None)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_full_dry_run_pipeline_emits_step_spans(spans: InMemorySpanExporter) -> None:
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

    span_names = {s.name for s in spans.get_finished_spans()}
    assert {"smoke.collect", "smoke.dedup", "smoke.publish", "smoke.notify"} <= span_names
