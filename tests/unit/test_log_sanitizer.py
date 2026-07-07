"""[X-U1] Значения секретов не встречаются ни в одном лог-выводе."""

import io
import logging

import pytest
import structlog

from app.obs.logging import configure_logging

SECRETS = ["123456:test-telegram-token", "sk-or-test-key", "p@ssw0rd-dsn"]


@pytest.fixture()
def log_output() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(secret_values=SECRETS, stream=stream)
    yield stream
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def test_secret_values_masked_in_message(log_output: io.StringIO) -> None:
    log = structlog.get_logger("test")
    log.info("llm call", api_key="sk-or-test-key", note="token 123456:test-telegram-token used")

    text = log_output.getvalue()
    assert text, "лог-вывод пуст"
    for secret in SECRETS:
        assert secret not in text
    assert "***" in text


def test_secrets_masked_in_nested_payload(log_output: io.StringIO) -> None:
    log = structlog.get_logger("test")
    log.warning("config dump", payload={"dsn": "p@ssw0rd-dsn", "list": ["sk-or-test-key", 1]})

    text = log_output.getvalue()
    for secret in SECRETS:
        assert secret not in text


def test_logs_are_json_with_event(log_output: io.StringIO) -> None:
    structlog.get_logger("test").info("hello_event", value=42)
    assert '"event": "hello_event"' in log_output.getvalue()
