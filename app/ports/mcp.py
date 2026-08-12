"""Реестр MCP-инструментов и порт бэкенда (спека 006, US7, MCP1–MCP2).

Тонкий интерфейсный слой: MCP-инструменты — обёртки над use cases приложения.
`McpBackend` — порт, который реализует композиционный корень (app/runtime), скрывая
за собой Services/репозитории. Слой `app/mcp` НЕ импортирует persistence/SQLAlchemy
(MCP1, import-linter): он оперирует этим портом и реестром.

Инвариант MCP2 (белый список write): изменять состояние могут только `set_status`
и `run_digest`; попытка зарегистрировать любой другой write-инструмент → ошибка
конфигурации (`WhitelistViolation`) ещё на этапе сборки сервера — небезопасный
инструмент не доедет до рантайма.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

__all__ = [
    "AUTH_ARG_HINT",
    "WRITE_WHITELIST",
    "McpBackend",
    "ToolHandler",
    "ToolRegistry",
    "ToolSpec",
    "WhitelistViolation",
    "build_registry",
]

# MCP2 ([P-U1]): единственные write-инструменты. Всё остальное — только чтение.
WRITE_WHITELIST: frozenset[str] = frozenset({"set_status", "run_digest"})

# Подсказка клиенту: каждый вызов должен нести auth-токен полем `auth_token` (MCP3).
AUTH_ARG_HINT = "Требует поле `auth_token` (MCP_AUTH_TOKEN) в аргументах вызова."

ToolHandler = Callable[..., Awaitable[Any]]


class WhitelistViolation(ValueError):
    """Регистрация write-инструмента вне `WRITE_WHITELIST` (MCP2)."""


class McpBackend(Protocol):
    """Порт бэкенда MCP: методы возвращают JSON-сериализуемые структуры.

    Реализация (`app/runtime`) прячет за собой сессии БД, репозитории и use cases;
    сам слой `app/mcp` работает только через этот порт (MCP1).
    """

    async def list_vacancies(
        self, *, min_score: int | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Список вакансий хранилища (новейшие первыми), опц. фильтр по скору."""
        ...

    async def get_vacancy(self, vacancy_id: int) -> dict[str, Any] | None:
        """Одна вакансия по PK или None."""
        ...

    async def search_saved(self, query: str) -> list[dict[str, Any]]:
        """Поиск по title/company/описанию (регистронезависимо)."""
        ...

    async def get_costs(self, days: int = 30) -> dict[str, Any]:
        """Затраты LLM за период (сумма cost_usd/токенов, разбивка по purpose)."""
        ...

    async def funnel_stats(self) -> dict[str, Any]:
        """Воронка заявок + счётчики хранилища/разметки."""
        ...

    async def set_status(
        self, vacancy_id: int, status: str, reject_stage: str | None = None
    ) -> dict[str, Any]:
        """Перевод заявки по статусной машине (write, whitelisted)."""
        ...

    async def run_digest(self, dry_run: bool = True) -> dict[str, Any]:
        """Запуск дайджеста; dry_run=true → «ТЕСТ», без внешних записей (write)."""
        ...


@dataclass(frozen=True)
class ToolSpec:
    """Описание MCP-инструмента: имя, флаг записи и async-обработчик."""

    name: str
    description: str
    write: bool
    handler: ToolHandler


class ToolRegistry:
    """Реестр инструментов с проверкой белого списка write (MCP2)."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.write and spec.name not in WRITE_WHITELIST:
            raise WhitelistViolation(
                f"write-инструмент {spec.name!r} вне белого списка {sorted(WRITE_WHITELIST)} (MCP2)"
            )
        if spec.name in self._specs:
            raise ValueError(f"инструмент {spec.name!r} уже зарегистрирован")
        self._specs[spec.name] = spec

    @property
    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def names(self) -> set[str]:
        return set(self._specs)


def build_registry(backend: McpBackend) -> ToolRegistry:
    """Собрать реестр 7 инструментов поверх бэкенда (5 read + 2 write из whitelist).

    Каждый обработчик — тонкая типизированная обёртка (FastMCP строит схему по
    аннотациям) над соответствующим методом `McpBackend`.
    """
    reg = ToolRegistry()

    async def list_vacancies(min_score: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Список сохранённых вакансий (новейшие первыми). Фильтр min_score опционален."""
        return await backend.list_vacancies(min_score=min_score, limit=limit)

    async def get_vacancy(vacancy_id: int) -> dict[str, Any] | None:
        """Одна вакансия по её id."""
        return await backend.get_vacancy(vacancy_id)

    async def search_saved(query: str) -> list[dict[str, Any]]:
        """Поиск по названию/компании/описанию сохранённых вакансий."""
        return await backend.search_saved(query)

    async def get_costs(days: int = 30) -> dict[str, Any]:
        """Затраты на LLM за последние `days` дней."""
        return await backend.get_costs(days)

    async def funnel_stats() -> dict[str, Any]:
        """Воронка заявок и счётчики хранилища/разметки."""
        return await backend.funnel_stats()

    async def set_status(
        vacancy_id: int, status: str, reject_stage: str | None = None
    ) -> dict[str, Any]:
        """Сменить статус заявки по вакансии (проходит статусную машину)."""
        return await backend.set_status(vacancy_id, status, reject_stage)

    async def run_digest(dry_run: bool = True) -> dict[str, Any]:
        """Запустить дайджест. dry_run=true — прогон «ТЕСТ» без внешних записей."""
        return await backend.run_digest(dry_run)

    reg.register(ToolSpec("list_vacancies", "Список сохранённых вакансий", False, list_vacancies))
    reg.register(ToolSpec("get_vacancy", "Вакансия по id", False, get_vacancy))
    reg.register(ToolSpec("search_saved", "Поиск по сохранённым вакансиям", False, search_saved))
    reg.register(ToolSpec("get_costs", "Затраты LLM за период", False, get_costs))
    reg.register(ToolSpec("funnel_stats", "Воронка заявок", False, funnel_stats))
    reg.register(ToolSpec("set_status", "Сменить статус заявки", True, set_status))
    reg.register(ToolSpec("run_digest", "Запустить дайджест (dry_run)", True, run_digest))
    return reg
