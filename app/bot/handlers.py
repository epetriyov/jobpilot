"""Хендлеры бота — тонкие: разбор апдейта → use case → рендер ответа."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.adapters.telegram.analytics_cards import (
    build_review_keyboard,
    parse_review_callback,
    render_costs,
    render_funnel,
    render_review_candidate,
    render_review_summary,
)
from app.adapters.telegram.cards import (
    parse_cover_callback,
    parse_invite_callback,
    parse_label_callback,
)
from app.adapters.telegram.crm_cards import (
    CrmCallback,
    build_saved_keyboard,
    parse_crm_callback,
    render_saved_text,
)
from app.application.review_agreement import ReviewCandidate, ReviewSummary
from app.domain.correspondence import COVER_LETTER_MAX_CHARS
from app.domain.crm import ApplicationStatus, InterviewRoundKind, RejectStage
from app.runtime.composition import Services

router = Router()


class CoverEdit(StatesGroup):
    """FSM ручной правки письма (✏️): ждём исправленный текст от владельца."""

    waiting_text = State()


class ReviewFlow(StatesGroup):
    """FSM пошагового /review (6C): показываем скоренные вакансии по одной, копим вердикты."""

    reviewing = State()


TRAIN_GOAL = 30  # цель разметки этапа 1 ([R-E1])
REVIEW_SAMPLE = 10  # сколько скоренных вакансий показать за один /review ([C-E2])
DEFAULT_COSTS_DAYS = 30  # окно /costs по умолчанию


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "JobPilot на связи. Команды:\n"
        "/digest — дайджест вакансий сейчас\n"
        "/saved — сохранённые заявки (CRM) и их статусы\n"
        "/iv <id> <ссылка> | <заметка> — детали собеса к заявке\n"
        "/train — прогресс разметки 👍/👎\n"
        "/stats — воронка заявок и конверсии\n"
        "/costs [дней] — затраты LLM за период\n"
        "/review — сверить скор со своими вердиктами (agreement rate)\n"
        "/publish — поднять резюме\n"
        "/invites — пакет инвайтов LinkedIn\n"
        "/invites_pending — неотправленные\n"
        "/invites_status — воронка нетворкинга\n"
        "/approve_scraper <site> — одобрить сайт-скрейпер из canary\n"
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


@router.message(Command("approve_scraper"))
async def cmd_approve_scraper(message: Message, services: Services) -> None:
    """US3: владелец одобряет canary-сайт → его вакансии в основной поток дайджеста."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажи сайт: /approve_scraper <site>")
        return
    site = parts[1].strip().lower()
    outcome, available = await services.approve_scraper(site)
    if outcome == "unknown":
        await message.answer(f"Неизвестный сайт «{site}». Доступные: " + ", ".join(available))
    elif outcome == "already":
        await message.answer(f"Сайт {site} уже одобрен ранее ✅")
    else:
        await message.answer(f"Сайт {site} одобрен — вакансии пойдут в основной поток дайджеста ✅")


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


@router.message(Command("saved"))
async def cmd_saved(message: Message, services: Services) -> None:
    """US2: список заявок CRM с контекстными кнопками статусов/раундов/отказа."""
    views = await services.saved_applications()
    if not views:
        await message.answer("Заявок пока нет. Жми 💾 Сохранить на карточке вакансии.")
        return
    for view in views:
        await message.answer(render_saved_text(view), reply_markup=build_saved_keyboard(view))


@router.message(Command("iv"))
async def cmd_iv(message: Message, services: Services) -> None:
    """US3 (ручной путь, [C-U5]): «➕ собес» — дополняет детали, статус НЕ меняет (C3).

    Формат: /iv <vacancy_id> <ссылка> | <заметка>
    """
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /iv <id вакансии> <ссылка> | <заметка>")
        return
    try:
        vacancy_id = int(parts[1])
    except ValueError:
        await message.answer("id вакансии должен быть числом.")
        return
    url_part, sep, notes_part = parts[2].partition("|")
    url = url_part.strip() or None
    notes = notes_part.strip() if sep else None
    outcome = await services.add_interview_details(vacancy_id, url=url, notes=notes or None)
    if outcome == "not_found":
        await message.answer("Заявка не найдена — сначала 💾 Сохранить вакансию.")
    else:
        await message.answer("Записал детали собеса ➕ (статус не менял).")


@router.message(Command("stats"))
async def cmd_stats(message: Message, services: Services) -> None:
    """US4 (6C): воронка заявок по статусам + конверсии + счётчики хранилища/разметки."""
    report = await services.funnel_stats()
    await message.answer(render_funnel(report))


@router.message(Command("costs"))
async def cmd_costs(message: Message, services: Services) -> None:
    """US4 (6C): сумма затрат LLM за период (по умолчанию 30 дней). `/costs 7` — за неделю."""
    parts = (message.text or "").split()
    days = DEFAULT_COSTS_DAYS
    if len(parts) > 1:
        try:
            days = int(parts[1])
        except ValueError:
            days = DEFAULT_COSTS_DAYS
    report = await services.report_costs(days)
    await message.answer(render_costs(report))


@router.message(Command("review"))
async def cmd_review(message: Message, services: Services, state: FSMContext) -> None:
    """US4 ([C-E2]): показать N скоренных вакансий по одной; вердикты копятся в FSM."""
    candidates = await services.start_review(REVIEW_SAMPLE)
    if not candidates:
        await message.answer("Нет скоренных вакансий для ревью — сначала собери дайджест.")
        return
    await state.set_state(ReviewFlow.reviewing)
    await state.update_data(
        queue=[c.model_dump(mode="json") for c in candidates],
        index=0,
        agreed=0,
    )
    await message.answer(
        render_review_candidate(candidates[0], index=0, total=len(candidates)),
        reply_markup=build_review_keyboard(),
    )


async def _dispatch_crm(services: Services, cb: CrmCallback) -> str:
    """Колбэк CRM → доменный метод через use case. Мэппинг исхода → вежливый ответ."""
    not_found = "Заявка не найдена — сначала 💾 Сохранить."
    illegal = "Так по воронке нельзя (переходы только вперёд, §3.3)."
    if cb.action == "save":
        return {
            "saved": "Сохранил 💾",
            "already": "Уже сохранена ранее ✅",
            "not_found": "Вакансия не найдена в хранилище 🤔",
        }[await services.save_vacancy(cb.vacancy_id)]
    if cb.action == "del":
        outcome = await services.delete_application(cb.vacancy_id)
        return "Удалил 🗑" if outcome == "deleted" else not_found
    if cb.action == "iv":
        return "Пришли детали: /iv " + str(cb.vacancy_id) + " <ссылка> | <заметка>"
    if cb.arg is None:
        return "Не разобрал кнопку 🤔"
    try:
        if cb.action == "adv":
            outcome = await services.advance_application(cb.vacancy_id, ApplicationStatus(cb.arg))
        elif cb.action == "rnd":
            outcome = await services.add_application_round(
                cb.vacancy_id, InterviewRoundKind(cb.arg)
            )
        elif cb.action == "rej":
            outcome = await services.reject_application(cb.vacancy_id, RejectStage(cb.arg))
        else:
            return "Неизвестное действие 🤔"
    except ValueError:
        return "Не разобрал кнопку 🤔"
    return {"ok": "Готово ✅", "illegal": illegal, "not_found": not_found}[outcome]


@router.callback_query(F.data.startswith("crm:"))
async def on_crm(callback: CallbackQuery, services: Services) -> None:
    try:
        cb = parse_crm_callback(callback.data or "")
    except ValueError:
        await callback.answer()
        return
    await callback.answer(await _dispatch_crm(services, cb))


@router.callback_query(F.data.startswith("cover:"))
async def on_cover(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    """✉️/🔁/✏️: генерация письма Pro по вакансии; отправку делает владелец вручную."""
    try:
        action, vacancy_id = parse_cover_callback(callback.data or "")
    except ValueError:
        await callback.answer()
        return

    if action == "edit":
        await state.set_state(CoverEdit.waiting_text)
        await state.update_data(vacancy_id=vacancy_id)
        await callback.answer()
        await callback.message.answer(  # type: ignore[union-attr]
            "✏️ Пришлите исправленный текст письма ответным сообщением "
            f"(до {COVER_LETTER_MAX_CHARS} знаков)."
        )
        return

    await callback.answer("Генерирую письмо…" if action == "new" else "Перегенерирую…")
    result = await services.generate_cover_letter(vacancy_id)
    if result.status == "generated":
        return  # карточка письма уже отправлена use case'ом
    # not_found / llm_failed — use case уже уведомил владельца


@router.message(CoverEdit.waiting_text)
async def on_cover_edit_text(message: Message, services: Services, state: FSMContext) -> None:
    """Ручная правка письма: сохраняем присланный текст как новую версию (data-model §4)."""
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой текст — правка не сохранена. Пришлите текст письма.")
        return
    if len(text) > COVER_LETTER_MAX_CHARS:
        await message.answer(
            f"Слишком длинно ({len(text)} > {COVER_LETTER_MAX_CHARS}). Сократите и пришлите снова."
        )
        return
    data = await state.get_data()
    vacancy_id = int(data["vacancy_id"])
    await state.clear()
    await services.save_cover_edit(vacancy_id, text)


@router.callback_query(ReviewFlow.reviewing, F.data.startswith("rev:"))
async def on_review(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    """Вердикт владельца в диалоге /review: сверка со скором, запись расхождений, шаг вперёд.

    Зарегистрирован ДО catch-all `on_label` — иначе тот перехватит `rev:*` ([C-E2]).
    """
    try:
        verdict = parse_review_callback(callback.data or "")
    except ValueError:
        await callback.answer()
        return

    data = await state.get_data()
    queue = data["queue"]
    index = int(data["index"])
    agreed = int(data["agreed"])

    current = ReviewCandidate.model_validate(queue[index])
    recorded = await services.record_review_verdict(current, verdict)
    if recorded.agreed:
        agreed += 1
    index += 1
    await callback.answer("Совпало со скором ✅" if recorded.agreed else "Расхождение записано 📝")

    if index < len(queue):
        await state.update_data(index=index, agreed=agreed)
        nxt = ReviewCandidate.model_validate(queue[index])
        await callback.message.answer(  # type: ignore[union-attr]
            render_review_candidate(nxt, index=index, total=len(queue)),
            reply_markup=build_review_keyboard(),
        )
        return

    summary = ReviewSummary.of(agreed=agreed, total=len(queue))
    await state.clear()
    await callback.message.answer(render_review_summary(summary))  # type: ignore[union-attr]


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
