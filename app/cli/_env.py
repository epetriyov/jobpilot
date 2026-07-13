"""Чтение переменных для CLI-хелперов: окружение → локальный .env (фолбэк).

Хелперы запускаются владельцем из корня репо; значения из .env не должны
требовать ручного экспорта в оболочку.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def read_env_var(name: str, env_file: Path = Path(".env")) -> str | None:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def ask(prompt: str, env_var: str) -> str:
    value = read_env_var(env_var)
    if value:
        print(f"{env_var}: взят из .env/окружения")
        return value
    value = input(f"{prompt}: ").strip()
    if not value:
        print("Пустое значение — выходим.", file=sys.stderr)
        raise SystemExit(1)
    return value
