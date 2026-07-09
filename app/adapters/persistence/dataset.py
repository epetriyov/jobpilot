"""JsonlDatasetAppender — реализация DatasetAppenderPort (append-only, [T112]).

Формат строки — Приложение TEST_CASES.md; added_at проставляется на записи.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlDatasetAppender:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, example: dict[str, Any]) -> None:
        example.setdefault("meta", {})["added_at"] = datetime.now(UTC).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
