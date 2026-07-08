"""Полная инициализация OTel: трейсы + метрики + логи → Alloy (OTLP/gRPC).

Единая точка входа для bot/worker/smoke — setup_telemetry(). Провайдеры
регистрируют atexit-shutdown, поэтому короткоживущие процессы (smoke)
доставляют данные при выходе. Недоступный коллектор не роняет сервис —
экспортёры батчевые и ретраятся в фоне.
"""

from __future__ import annotations

import logging
from typing import cast

from opentelemetry import metrics as otel_metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from app.obs.tracing import setup_tracing


def _resource(service_name: str) -> Resource:
    return Resource.create({"service.name": service_name})


def setup_metrics(
    *,
    service_name: str,
    otlp_endpoint: str | None = None,
    reader: MetricReader | None = None,
) -> MeterProvider:
    """Настроить MeterProvider; reader передают тесты (in-memory)."""
    readers: list[MetricReader] = []
    if reader is not None:
        readers = [reader]
    elif otlp_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        readers = [
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
                export_interval_millis=15_000,
            )
        ]
    provider = MeterProvider(resource=_resource(service_name), metric_readers=readers)
    otel_metrics.set_meter_provider(provider)
    return provider


def setup_log_export(
    *,
    service_name: str,
    otlp_endpoint: str | None = None,
    exporter: LogExporter | None = None,
) -> LoggerProvider:
    """Мост stdlib logging → OTLP (Loki в Grafana Cloud).

    structlog рендерит JSON через stdlib-логгер, поэтому хендлер на root
    пересылает уже санитизированные строки ([X-U1] действует и для Loki).
    """
    if exporter is None and otlp_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

        exporter = cast("LogExporter", OTLPLogExporter(endpoint=otlp_endpoint, insecure=True))

    provider = LoggerProvider(resource=_resource(service_name))
    if exporter is not None:
        provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))
    return provider


def setup_telemetry(*, service_name: str, otlp_endpoint: str | None) -> None:
    """Трейсы + метрики + логи одним вызовом. Вызывать ПОСЛЕ configure_logging."""
    setup_tracing(service_name=service_name, otlp_endpoint=otlp_endpoint)
    setup_metrics(service_name=service_name, otlp_endpoint=otlp_endpoint)
    setup_log_export(service_name=service_name, otlp_endpoint=otlp_endpoint)
