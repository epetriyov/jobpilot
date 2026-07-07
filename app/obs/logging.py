"""structlog JSON + санитайзер секретов ([X-U1], AGENT_GUIDE.md §5).

В логи запрещены: значения секретов, тела писем, полные тексты промптов.
Санитайзер — константная защита: любое вхождение значения секрета
в любом поле события заменяется на ***.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable, MutableMapping
from typing import Any, TextIO

import structlog

MASK = "***"


def _mask_value(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret and secret in value:
                value = value.replace(secret, MASK)
        return value
    if isinstance(value, dict):
        return {k: _mask_value(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_mask_value(v, secrets) for v in value)
    return value


def make_sanitizer(
    secret_values: Iterable[str],
) -> structlog.types.Processor:
    secrets = sorted((s for s in secret_values if s), key=len, reverse=True)

    def sanitize(
        logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        for key, value in event_dict.items():
            event_dict[key] = _mask_value(value, secrets)
        return event_dict

    return sanitize


def configure_logging(
    *, secret_values: Iterable[str] = (), stream: TextIO | None = None
) -> None:
    """Настроить structlog: JSON в stdout, ISO-время, санитайзер секретов."""
    logging.basicConfig(
        format="%(message)s", stream=stream or sys.stdout, level=logging.INFO, force=True
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            make_sanitizer(secret_values),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
