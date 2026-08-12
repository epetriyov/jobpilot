"""[C-I1] Бот-хендлеры CRM (aiogram harness на фейках): 💾/статусы/раунды/🗑/➕ собес.

Хендлеры тонкие: разбирают апдейт → services (use case) → вежливый ответ. Здесь
проверяем маршрутизацию колбэков `crm:*` и команды `/saved`, `/iv` без реальной БД.
"""

from __future__ import annotations

from typing import Any

from app.adapters.telegram.crm_cards import SavedApplicationView
from app.bot.handlers import cmd_iv, cmd_saved, on_crm


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answered: list[str] = []

    async def answer(self, text: str = "", **_: Any) -> None:
        self.answered.append(text)


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []
        self.markups: list[Any] = []

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.replies.append(text)
        self.markups.append(reply_markup)


class FakeServices:
    """Duck-typed заглушка Services: фиксирует вызовы, отдаёт заданные исходы."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.save_outcome = "saved"
        self.advance_outcome = "ok"
        self.round_outcome = "ok"
        self.reject_outcome = "ok"
        self.delete_outcome = "deleted"
        self.details_outcome = "ok"
        self.saved: list[SavedApplicationView] = []

    async def save_vacancy(self, vacancy_id: int) -> str:
        self.calls.append(("save", (vacancy_id,)))
        return self.save_outcome

    async def advance_application(self, vacancy_id: int, to: Any) -> str:
        self.calls.append(("advance", (vacancy_id, str(to))))
        return self.advance_outcome

    async def add_application_round(self, vacancy_id: int, kind: Any) -> str:
        self.calls.append(("round", (vacancy_id, str(kind))))
        return self.round_outcome

    async def reject_application(self, vacancy_id: int, stage: Any) -> str:
        self.calls.append(("reject", (vacancy_id, str(stage))))
        return self.reject_outcome

    async def delete_application(self, vacancy_id: int) -> str:
        self.calls.append(("delete", (vacancy_id,)))
        return self.delete_outcome

    async def add_interview_details(
        self, vacancy_id: int, *, url: str | None = None, notes: str | None = None
    ) -> str:
        self.calls.append(("details", (vacancy_id, url, notes)))
        return self.details_outcome

    async def saved_applications(self) -> list[SavedApplicationView]:
        return self.saved


async def test_save_callback_routes_to_save() -> None:
    services = FakeServices()
    cb = FakeCallback("crm:save:42")
    await on_crm(cb, services)  # type: ignore[arg-type]
    assert services.calls == [("save", (42,))]
    assert "Сохранил" in cb.answered[0]


async def test_advance_callback_passes_status() -> None:
    services = FakeServices()
    await on_crm(FakeCallback("crm:adv:applied:7"), services)  # type: ignore[arg-type]
    assert services.calls == [("advance", (7, "applied"))]


async def test_round_callback_passes_kind() -> None:
    services = FakeServices()
    await on_crm(FakeCallback("crm:rnd:tech-1:7"), services)  # type: ignore[arg-type]
    assert services.calls == [("round", (7, "tech-1"))]


async def test_reject_callback_passes_stage() -> None:
    services = FakeServices()
    await on_crm(FakeCallback("crm:rej:pre_hr:7"), services)  # type: ignore[arg-type]
    assert services.calls == [("reject", (7, "pre_hr"))]


async def test_illegal_outcome_is_polite() -> None:
    services = FakeServices()
    services.advance_outcome = "illegal"
    cb = FakeCallback("crm:adv:offer:7")
    await on_crm(cb, services)  # type: ignore[arg-type]
    assert "нельзя" in cb.answered[0].lower()


async def test_delete_callback() -> None:
    services = FakeServices()
    cb = FakeCallback("crm:del:7")
    await on_crm(cb, services)  # type: ignore[arg-type]
    assert services.calls == [("delete", (7,))]
    assert "Удалил" in cb.answered[0]


async def test_iv_callback_prompts_command() -> None:
    services = FakeServices()
    cb = FakeCallback("crm:iv:7")
    await on_crm(cb, services)  # type: ignore[arg-type]
    assert services.calls == []  # кнопка только подсказывает
    assert "/iv 7" in cb.answered[0]


async def test_garbage_callback_silent() -> None:
    services = FakeServices()
    cb = FakeCallback("noise:1")
    await on_crm(cb, services)  # type: ignore[arg-type]
    assert services.calls == []
    assert cb.answered == [""]  # тихий answer без текста


async def test_saved_empty() -> None:
    services = FakeServices()
    msg = FakeMessage("/saved")
    await cmd_saved(msg, services)  # type: ignore[arg-type]
    assert "Заявок пока нет" in msg.replies[0]


async def test_saved_renders_cards() -> None:
    services = FakeServices()
    services.saved = [
        SavedApplicationView(
            vacancy_id=7, title="EM", company="Acme", status="interview", rounds=["hr"]
        )
    ]
    msg = FakeMessage("/saved")
    await cmd_saved(msg, services)  # type: ignore[arg-type]
    assert "EM" in msg.replies[0]
    assert msg.markups[0] is not None  # клавиатура с кнопками


async def test_iv_command_parses_url_and_notes() -> None:
    services = FakeServices()
    msg = FakeMessage("/iv 7 https://meet.example/x | звонок в 15:00")
    await cmd_iv(msg, services)  # type: ignore[arg-type]
    assert services.calls == [("details", (7, "https://meet.example/x", "звонок в 15:00"))]
    assert "Записал детали" in msg.replies[0]


async def test_iv_command_bad_id() -> None:
    services = FakeServices()
    msg = FakeMessage("/iv abc ссылка")
    await cmd_iv(msg, services)  # type: ignore[arg-type]
    assert services.calls == []
    assert "числом" in msg.replies[0]


async def test_iv_command_usage_hint() -> None:
    services = FakeServices()
    msg = FakeMessage("/iv 7")
    await cmd_iv(msg, services)  # type: ignore[arg-type]
    assert services.calls == []
    assert "Формат" in msg.replies[0]
