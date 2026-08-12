"""T6F-2 [P-U1] (MCP2): белый список write-инструментов реестра.

Фабрика падает при регистрации write вне `{set_status, run_digest}`; тест перебирает
все зарегистрированные инструменты и проверяет их флаги.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ports.mcp import (
    WRITE_WHITELIST,
    McpBackend,
    ToolRegistry,
    ToolSpec,
    WhitelistViolation,
    build_registry,
)


async def _noop() -> dict[str, Any]:
    return {}


def test_whitelist_is_exactly_two() -> None:
    assert frozenset({"set_status", "run_digest"}) == WRITE_WHITELIST


def test_register_write_outside_whitelist_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(WhitelistViolation):
        reg.register(ToolSpec("delete_everything", "danger", write=True, handler=_noop))


@pytest.mark.parametrize("name", sorted(WRITE_WHITELIST))
def test_register_whitelisted_write_ok(name: str) -> None:
    reg = ToolRegistry()
    reg.register(ToolSpec(name, "ok", write=True, handler=_noop))
    assert reg.names() == {name}


def test_register_read_tool_ok() -> None:
    reg = ToolRegistry()
    reg.register(ToolSpec("some_read", "read", write=False, handler=_noop))
    assert reg.names() == {"some_read"}


def test_duplicate_registration_raises() -> None:
    reg = ToolRegistry()
    reg.register(ToolSpec("x", "x", write=False, handler=_noop))
    with pytest.raises(ValueError):
        reg.register(ToolSpec("x", "x", write=False, handler=_noop))


def test_build_registry_write_tools_are_subset(fake_backend: McpBackend) -> None:
    reg = build_registry(fake_backend)
    writes = {s.name for s in reg.specs if s.write}
    assert writes == set(WRITE_WHITELIST)
    for spec in reg.specs:
        if spec.name in WRITE_WHITELIST:
            assert spec.write is True
        else:
            assert spec.write is False


def test_build_registry_exposes_all_tools(fake_backend: McpBackend) -> None:
    reg = build_registry(fake_backend)
    assert reg.names() == {
        "list_vacancies",
        "get_vacancy",
        "search_saved",
        "get_costs",
        "funnel_stats",
        "set_status",
        "run_digest",
    }
