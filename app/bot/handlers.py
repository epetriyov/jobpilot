"""Хендлеры бота — тонкие: разбор апдейта → ответ. Бизнес-логики здесь нет."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "JobPilot на связи. Этап 0 — фундамент. Доступно: /ping.\n"
        "Дайджесты и команды поиска появятся на следующих этапах."
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong 🟢")
