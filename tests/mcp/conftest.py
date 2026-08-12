"""Фикстуры MCP-тестов: детерминированный in-memory бэкенд (без БД, без сети)."""

from __future__ import annotations

from typing import Any

import pytest

from app.ports.mcp import McpBackend


class FakeBackend:
    """In-memory реализация McpBackend: фиксированные ответы + журнал вызовов."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._vacancies: dict[int, dict[str, Any]] = {
            1: {"id": 1, "title": "EM", "company": "Acme", "score": 80},
            2: {"id": 2, "title": "Head of Eng", "company": "Globex", "score": 55},
        }

    def _log(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    async def list_vacancies(
        self, *, min_score: int | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        self._log("list_vacancies", min_score=min_score, limit=limit)
        rows = sorted(self._vacancies.values(), key=lambda r: -r["id"])
        if min_score is not None:
            rows = [r for r in rows if r["score"] >= min_score]
        return rows[:limit]

    async def get_vacancy(self, vacancy_id: int) -> dict[str, Any] | None:
        self._log("get_vacancy", vacancy_id)
        return self._vacancies.get(vacancy_id)

    async def search_saved(self, query: str) -> list[dict[str, Any]]:
        self._log("search_saved", query)
        q = query.lower()
        return [r for r in self._vacancies.values() if q in r["title"].lower()]

    async def get_costs(self, days: int = 30) -> dict[str, Any]:
        self._log("get_costs", days)
        return {"days": days, "total_usd": 1.23, "calls": 4}

    async def funnel_stats(self) -> dict[str, Any]:
        self._log("funnel_stats")
        return {"total": 2, "counts": {"new": 1, "applied": 1}}

    async def set_status(
        self, vacancy_id: int, status: str, reject_stage: str | None = None
    ) -> dict[str, Any]:
        self._log("set_status", vacancy_id, status, reject_stage)
        outcome = "ok" if status in {"applied", "interview", "offer", "rejected"} else "illegal"
        return {"outcome": outcome, "vacancy_id": vacancy_id, "status": status}

    async def run_digest(self, dry_run: bool = True) -> dict[str, Any]:
        self._log("run_digest", dry_run)
        return {"dry_run": dry_run, "discovered": 0, "cards_sent": 0, "label": "ТЕСТ"}


@pytest.fixture
def fake_backend() -> McpBackend:
    return FakeBackend()
