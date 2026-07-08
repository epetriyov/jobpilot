"""Экспорт метрик и логов OTel: счётчики и structlog-события реально уходят в пайплайн.

Без настроенного MeterProvider/LoggerProvider инкременты и логи молча теряются —
эти тесты охраняют «наблюдаемость — не опция» (constitution V) на уровне wiring.
"""

import logging

import structlog
from opentelemetry.sdk._logs.export import InMemoryLogExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.obs.logging import configure_logging
from app.obs.metrics import record_llm_metrics
from app.obs.telemetry import setup_log_export, setup_metrics


def test_metric_counters_reach_exporter() -> None:
    reader = InMemoryMetricReader()
    setup_metrics(service_name="test", reader=reader)

    record_llm_metrics(
        purpose="scoring", model="m", input_tokens=10, output_tokens=5, cost_usd=0.01
    )

    data = reader.get_metrics_data()
    names = {
        metric.name
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
    }
    assert "llm_tokens_total" in names
    assert "llm_cost_usd_total" in names


def test_structlog_events_reach_log_exporter() -> None:
    configure_logging(secret_values=["s3cret-value"])
    exporter = InMemoryLogExporter()
    setup_log_export(service_name="test", exporter=exporter)

    structlog.get_logger("test").warning("digest_failed", token="s3cret-value")
    logging.getLogger().handlers[-1].flush()

    bodies = [str(log_data.log_record.body) for log_data in exporter.get_finished_logs()]
    assert any("digest_failed" in body for body in bodies)
    # санитайзер отработал ДО экспорта: секрет не уходит в Loki
    assert all("s3cret-value" not in body for body in bodies)
