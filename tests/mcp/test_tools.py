"""T6F-4 [P-C1]: инструменты через реальный FastMCP-сервер (in-memory client).

Каждый инструмент вызывается сквозь сервер с auth-токеном и возвращает ожидаемое;
вызов без токена отвергается до инструмента (MCP3); write-инструменты работают по
белому списку (run_digest dry_run → «ТЕСТ»; set_status → outcome статусной машины).
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from app.mcp import build_mcp_server
from app.mcp.auth import AUTH_ARG
from tests.mcp.conftest import FakeBackend

TOKEN = "s3cret"


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def server(backend: FakeBackend):  # type: ignore[no-untyped-def]
    return build_mcp_server(backend, TOKEN, name="jobpilot-test")


async def test_lists_expected_tools(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {
        "list_vacancies",
        "get_vacancy",
        "search_saved",
        "get_costs",
        "funnel_stats",
        "set_status",
        "run_digest",
    }


async def test_list_vacancies_read(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        res = await client.call_tool("list_vacancies", {AUTH_ARG: TOKEN, "min_score": 60})
    assert [r["id"] for r in res.data] == [1]


async def test_get_vacancy_read(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        res = await client.call_tool("get_vacancy", {AUTH_ARG: TOKEN, "vacancy_id": 2})
    assert res.data["company"] == "Globex"


async def test_search_and_costs_and_funnel(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        found = await client.call_tool("search_saved", {AUTH_ARG: TOKEN, "query": "head"})
        costs = await client.call_tool("get_costs", {AUTH_ARG: TOKEN, "days": 7})
        funnel = await client.call_tool("funnel_stats", {AUTH_ARG: TOKEN})
    assert [r["id"] for r in found.data] == [2]
    assert costs.data["days"] == 7
    assert funnel.data["total"] == 2


async def test_run_digest_dry_run_says_test(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        res = await client.call_tool("run_digest", {AUTH_ARG: TOKEN, "dry_run": True})
    assert res.data["dry_run"] is True
    assert res.data["label"] == "ТЕСТ"


async def test_set_status_illegal_rejected(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        ok = await client.call_tool(
            "set_status", {AUTH_ARG: TOKEN, "vacancy_id": 1, "status": "applied"}
        )
        bad = await client.call_tool(
            "set_status", {AUTH_ARG: TOKEN, "vacancy_id": 1, "status": "bogus"}
        )
    assert ok.data["outcome"] == "ok"
    assert bad.data["outcome"] == "illegal"


async def test_call_without_token_is_denied(server, backend: FakeBackend) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as client:
        with pytest.raises(Exception):  # noqa: B017 — FastMCP оборачивает AuthError в ToolError
            await client.call_tool("funnel_stats", {})
    # инструмент не вызван (MCP3)
    assert all(name != "funnel_stats" for name, _a, _k in backend.calls)
