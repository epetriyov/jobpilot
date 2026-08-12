"""T6F-1 [P-C2] (MCP1): слой app/mcp не тянет persistence/SQLAlchemy/runtime.

Арх-тест дублирует import-linter контракт (быстрая обратная связь при рефакторинге):
статический разбор всех модулей `app/mcp` — ни одного импорта запрещённого слоя.
"""

from __future__ import annotations

import ast
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parents[2] / "app" / "mcp"
_FORBIDDEN_PREFIXES = (
    "sqlalchemy",
    "alembic",
    "app.adapters",
    "app.runtime",
    "app.config",
)


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_app_mcp_has_no_persistence_imports() -> None:
    files = list(_MCP_DIR.rglob("*.py"))
    assert files, "модули app/mcp не найдены"
    for py in files:
        for module in _imported_modules(py.read_text(encoding="utf-8")):
            for forbidden in _FORBIDDEN_PREFIXES:
                assert not (module == forbidden or module.startswith(forbidden + ".")), (
                    f"{py.name}: запрещённый импорт {module!r} (MCP1)"
                )
