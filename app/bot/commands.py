"""Меню команд Telegram (синее меню по кнопке «/»).

Тонкий bot-слой: чистая функция-строитель `BotCommand`, вызывается один раз при
старте (`bot.set_my_commands`). Описания — краткие русские, источник — `/start`.
Множество имён обязано совпадать с зарегистрированными `Command(...)` хендлерами
(guard в tests/unit/test_bot_commands.py [B-U1]).
"""

from __future__ import annotations

from aiogram.types import BotCommand

# command → краткое русское описание (≤256, для базового имени команды).
_MENU: dict[str, str] = {
    "start": "Список команд и приветствие",
    "digest": "Дайджест вакансий сейчас",
    "saved": "Сохранённые заявки (CRM) и статусы",
    "iv": "Детали собеса к заявке вручную: /iv <id> <ссылка> | <заметка>",
    "hr": "Извлечь детали собеса из сообщения HR: /hr <id> <текст>",
    "train": "Прогресс разметки 👍/👎",
    "stats": "Воронка заявок и конверсии",
    "costs": "Затраты LLM за период: /costs [дней]",
    "review": "Сверить скор со своими вердиктами",
    "publish": "Поднять резюме",
    "invites": "Пакет инвайтов LinkedIn",
    "invites_pending": "Неотправленные инвайты",
    "invites_status": "Воронка нетворкинга",
    "approve_scraper": "Одобрить сайт-скрейпер из canary: /approve_scraper <site>",
    "ping": "Проверка связи",
}


def build_bot_commands() -> list[BotCommand]:
    """Меню команд для `bot.set_my_commands(...)`."""
    return [BotCommand(command=name, description=desc) for name, desc in _MENU.items()]
