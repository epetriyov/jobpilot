"""[B-U1] Меню команд Telegram синхронно с зарегистрированными хендлерами.

`build_bot_commands()` — чистая функция (без сети/БД): строит список `BotCommand`
для `bot.set_my_commands(...)`. Тест — guard от дрейфа: множество команд меню
обязано совпадать с множеством имён, реально зарегистрированных как `Command(...)`
хендлеры в роутере бота; плюс валидность имён/описаний и отсутствие дублей.
"""

from __future__ import annotations

import re

from aiogram.types import BotCommand

from app.bot.commands import build_bot_commands
from app.bot.handlers import router

_COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")


def _registered_command_names() -> set[str]:
    """Имена команд из фильтров `Command(...)` всех message-хендлеров роутера."""
    names: set[str] = set()
    for handler in router.message.handlers:
        for flt in handler.filters:
            commands = getattr(flt.callback, "commands", None)
            if commands:
                names.update(str(c) for c in commands)
    return names


def test_menu_matches_registered_handlers() -> None:
    menu_names = [c.command for c in build_bot_commands()]
    assert set(menu_names) == _registered_command_names()


def test_menu_has_no_duplicates() -> None:
    menu_names = [c.command for c in build_bot_commands()]
    assert len(menu_names) == len(set(menu_names))


def test_commands_are_valid() -> None:
    for cmd in build_bot_commands():
        assert isinstance(cmd, BotCommand)
        assert _COMMAND_RE.match(cmd.command), cmd.command
        assert cmd.description.strip()
        assert len(cmd.description) <= 256
