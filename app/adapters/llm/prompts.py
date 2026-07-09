"""Загрузка версионируемых промптов из adapters/llm/prompts/<purpose>_v<N>.md.

Промпт = файл (AGENT_GUIDE.md §4); изменение текста → новая версия N+1.
Использует секцию `## System` markdown-файла.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_system_prompt(purpose: str, version: int) -> str:
    """Вернуть текст system-инструкции промпта <purpose>_v<version>."""
    path = _PROMPTS_DIR / f"{purpose}_v{version}.md"
    text = path.read_text(encoding="utf-8")
    marker = "## System"
    if marker not in text:
        raise ValueError(f"в промпте {path.name} нет секции '{marker}'")
    section = text.split(marker, 1)[1]
    # до следующего заголовка того же уровня, если он есть
    for stop in ("\n## ", "\n# "):
        if stop in section:
            section = section.split(stop, 1)[0]
    return section.strip()
