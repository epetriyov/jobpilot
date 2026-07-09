"""Хендлеры бота — тонкие: разбор апдейта → use case → рендер ответа."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.adapters.telegram.cards import parse_label_callback
from app.runtime.composition import Services

router = Router()

TRAIN_GOAL = 30  # цель разметки этапа 1 ([R-E1])


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "JobPilot на связи. Команды:\n"
        "/digest — дайджест вакансий сейчас\n"
        "/train — прогресс разметки 👍/👎\n"
        "/publish — поднять резюме\n"
        "/ping — проверка связи"
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong 🟢")


@router.message(Command("digest"))
async def cmd_digest(message: Message, services: Services) -> None:
    await message.answer("Собираю дайджест…")
    result = await services.run_digest()
    if result.cards_sent == 0 and result.discovered == 0:
        await message.answer(
            "Готово: новых вакансий не найдено"
            + (" (источники HH ещё не подключены)." if not result.partial else ".")
        )


@router.message(Command("train"))
async def cmd_train(message: Message, services: Services) -> None:
    relevant, irrelevant = await services.train_progress()
    total = relevant + irrelevant
    remaining = max(0, TRAIN_GOAL - total)
    await message.answer(
        f"Размечено: {total} (👍 {relevant} / 👎 {irrelevant})\n"
        + (
            f"До цели eval ({TRAIN_GOAL}) осталось: {remaining}"
            if remaining
            else "Цель разметки достигнута — можно запускать eval 🎉"
        )
    )


@router.message(Command("publish"))
async def cmd_publish(message: Message, services: Services) -> None:
    result = await services.publish()
    replies = {
        "dry_run": "🧪 DRY_RUN: поднятие резюме пропущено (ТЕСТ).",
        "published": "Резюме поднято ⬆️",
        "skipped_limit": "Лимит HH: поднимать пока рано, жду следующий слот.",
    }
    await message.answer(replies[result.status])


@router.callback_query()
async def on_label(callback: CallbackQuery, services: Services) -> None:
    try:
        verdict, ref_key = parse_label_callback(callback.data or "")
    except ValueError:
        await callback.answer()
        return

    labeled = await services.label(ref_key, verdict)
    if labeled is None:
        await callback.answer("Не нашёл вакансию в реестре 🤔", show_alert=False)
        return
    await callback.answer("Записал 👍" if verdict == "relevant" else "Записал 👎")
