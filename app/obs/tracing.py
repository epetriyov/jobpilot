"""Инициализация OpenTelemetry: OTLP → Alloy (коллектор), недоступность не роняет сервис."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter


def setup_tracing(
    *,
    service_name: str,
    otlp_endpoint: str | None = None,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Настроить провайдер трейсов.

    exporter передаётся тестами (in-memory, [X-I1]); в бою — OTLP/gRPC на Alloy.
    Экспорт батчевый и неблокирующий: недоступный коллектор не влияет на пайплайн.
    """
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is None and otlp_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def current_trace_id() -> str:
    """Сквозной trace_id текущего спана (hex); нулевой, если спана нет."""
    span_context = trace.get_current_span().get_span_context()
    return format(span_context.trace_id, "032x")
