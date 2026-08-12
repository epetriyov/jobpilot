"""T6G-2: бот-хендлер `/hr` (LLM-путь «➕ собес») на aiogram-фейках.

Пересланное/приложенное HR-сообщение к сохранённой заявке → авто-извлечение
даты/ссылки/сути → предзаполнение деталей (статус не меняет, C3). Невалидно/пусто/
нет заявки → мягкий фолбэк на ручной ввод `/iv`.
"""

from __future__ import annotations

from typing import Any

from app.application.extract_hr_details import ExtractHrResult
from app.bot.handlers import cmd_hr


class FakeMessage:
    def __init__(self, text: str, reply_text: str | None = None) -> None:
        self.text = text
        self.replies: list[str] = []
        self.reply_to_message = _Reply(reply_text) if reply_text is not None else None

    async def answer(self, text: str, **_: Any) -> None:
        self.replies.append(text)


class _Reply:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeServices:
    def __init__(self, result: ExtractHrResult) -> None:
        self.result = result
        self.calls: list[tuple[int, str]] = []

    async def extract_hr_details(self, vacancy_id: int, *, message_text: str) -> ExtractHrResult:
        self.calls.append((vacancy_id, message_text))
        return self.result


async def test_hr_extracts_from_inline_text() -> None:
    services = FakeServices(
        ExtractHrResult(status="extracted", url="https://meet.example/x", notes="Дата: 2026-08-20")
    )
    msg = FakeMessage("/hr 7 Собес 2026-08-20, ссылка https://meet.example/x")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert services.calls == [(7, "Собес 2026-08-20, ссылка https://meet.example/x")]
    assert "статус" in msg.replies[0].lower()  # подтверждение «статус не менял»


async def test_hr_extracts_from_replied_message() -> None:
    """Reply на пересланное HR-сообщение: текст берётся из reply_to_message."""
    services = FakeServices(ExtractHrResult(status="extracted", url=None, notes="Дата: 2026-08-20"))
    msg = FakeMessage("/hr 7", reply_text="Приглашаем на собес 2026-08-20")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert services.calls == [(7, "Приглашаем на собес 2026-08-20")]
    assert msg.replies


async def test_hr_empty_falls_back_to_manual() -> None:
    services = FakeServices(ExtractHrResult(status="empty"))
    msg = FakeMessage("/hr 7 просто привет")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert "/iv 7" in msg.replies[0]  # мягкий фолбэк на ручной ввод


async def test_hr_llm_failed_falls_back_to_manual() -> None:
    services = FakeServices(ExtractHrResult(status="llm_failed"))
    msg = FakeMessage("/hr 7 что-то")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert "/iv 7" in msg.replies[0]


async def test_hr_not_found_prompts_save() -> None:
    services = FakeServices(ExtractHrResult(status="not_found"))
    msg = FakeMessage("/hr 7 Собес 2026-08-20")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert "Сохран" in msg.replies[0]


async def test_hr_bad_id() -> None:
    services = FakeServices(ExtractHrResult(status="extracted"))
    msg = FakeMessage("/hr abc текст")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert services.calls == []
    assert "числом" in msg.replies[0]


async def test_hr_usage_hint_when_no_text() -> None:
    services = FakeServices(ExtractHrResult(status="extracted"))
    msg = FakeMessage("/hr 7")
    await cmd_hr(msg, services)  # type: ignore[arg-type]
    assert services.calls == []
    assert "Формат" in msg.replies[0]
