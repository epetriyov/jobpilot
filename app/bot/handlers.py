"""Хендлеры бота — тонкие: разбор апдейта → use case → рендер ответа."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.adapters.telegram.cards import parse_invite_callback, parse_label_callback
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
        "/invites — пакет инвайтов LinkedIn\n"
        "/invites_pending — неотправленные\n"
        "/invites_status — воронка нетворкинга\n"
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


@router.message(Command("invites"))
async def cmd_invites(message: Message, services: Services) -> None:
    await message.answer("Готовлю пакет инвайтов…")
    result = await services.build_invites()
    if result.created == 0 and result.pending_reminder == 0:
        await message.answer("Новых заготовок нет.")


@router.message(Command("invites_pending"))
async def cmd_invites_pending(message: Message, services: Services) -> None:
    pending = await services.invites_pending()
    if not pending:
        await message.answer("Неотправленных инвайтов нет 🎉")
        return
    await message.answer("Неотправленные:\n\n" + "\n\n".join(pending[:20]))


@router.message(Command("invites_status"))
async def cmd_invites_status(message: Message, services: Services) -> None:
    counts = await services.invites_counts()
    await message.answer(
        "Воронка нетворкинга:\n"
        f"к отправке: {counts.get('proposed', 0)}\n"
        f"отправлено: {counts.get('sent', 0)}\n"
        f"принято: {counts.get('accepted', 0)}"
    )


@router.callback_query(F.data.startswith("inv:"))
async def on_invite_status(callback: CallbackQuery, services: Services) -> None:
    try:
        action, invite_id = parse_invite_callback(callback.data or "")
    except ValueError:
        await callback.answer()
        return
    outcome = await services.update_invite(invite_id, action)
    replies = {
        "ok": "Отметил: отправлен 📤" if action == "sent" else "Поздравляю, принят ✅",
        "illegal": "Статус уже финальный или переход не по порядку.",
        "not_found": "Не нашёл заготовку 🤔",
    }
    await callback.answer(replies[outcome])


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
