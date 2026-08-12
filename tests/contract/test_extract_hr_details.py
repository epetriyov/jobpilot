"""[C-U5]/T6G-2 контракт ExtractHrDetails: LLM-путь «➕ собес» из HR-сообщения.

Из пересланного HR-сообщения LLM извлекает дату/ссылку/суть → дополняет
interview_url/notes заявки через существующий AddInterviewDetails; статус НЕ
меняется (C3). llm_call учтён (O1). Тело сообщения не логируется (M4). Невалидный
вывод/пусто → мягкий фолбэк на ручной ввод (US3).
"""

from __future__ import annotations

import json

from app.adapters.llm.fake import FakeLlm, stub_hr_response
from app.application.add_interview_details import AddInterviewDetails
from app.application.extract_hr_details import ExtractHrDetails
from app.domain.crm import Application, ApplicationStatus
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord

PV = PromptVersion(purpose="hr_extract", version=1)
SYSTEM = "Извлеки дату, ссылку и суть из сообщения HR."


class FakeAppRepo:
    def __init__(self, apps: dict[int, Application] | None = None) -> None:
        self._by_vacancy = apps or {}
        self.save_calls = 0

    async def get_by_vacancy(self, vacancy_id: int) -> Application | None:
        app = self._by_vacancy.get(vacancy_id)
        return app.model_copy(deep=True) if app else None

    async def save(self, app: Application) -> int:
        self.save_calls += 1
        self._by_vacancy[app.vacancy_id] = app.model_copy(deep=True)
        return app.vacancy_id

    async def delete(self, vacancy_id: int) -> None:
        self._by_vacancy.pop(vacancy_id, None)

    async def list_all(self) -> list[Application]:
        return list(self._by_vacancy.values())

    async def funnel_counts(self) -> dict[str, int]:
        return {}


class RecorderSpy:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


def _make(*, repo: FakeAppRepo, llm: FakeLlm) -> ExtractHrDetails:
    return ExtractHrDetails(
        llm=llm,
        details=AddInterviewDetails(apps=repo),
        system_prompt=SYSTEM,
        prompt_version=PV,
    )


def _app_in_interview(vacancy_id: int = 7) -> Application:
    app = Application(vacancy_id=vacancy_id)
    app.apply()
    app.to_interview()
    return app


async def test_c_u5_extracts_and_fills_details_without_status_change() -> None:
    repo = FakeAppRepo({7: _app_in_interview(7)})
    rec = RecorderSpy()
    llm = FakeLlm(recorder=rec, model="fake/hr", response_factory=stub_hr_response)
    msg = "Здравствуйте! Собеседование 2026-08-20, ссылка https://meet.example/abc — Zoom."

    result = await _make(repo=repo, llm=llm).run(7, message_text=msg)

    assert result.status == "extracted"
    saved = await repo.get_by_vacancy(7)
    assert saved is not None
    # статус НЕ изменился (C3) — остался interview
    assert saved.status is ApplicationStatus.INTERVIEW
    # ссылка и суть (в т.ч. дата) записаны
    assert saved.interview_url == "https://meet.example/abc"
    assert saved.notes is not None
    assert "2026-08-20" in saved.notes
    # llm_call учтён (O1), purpose=hr_extract, версия промпта
    assert len(rec.records) == 1
    assert rec.records[0].purpose == "hr_extract"
    assert rec.records[0].prompt_version == "hr_extract_v1"


async def test_c_u5_message_body_is_untrusted_data() -> None:
    """R5: текст HR подаётся как недоверенные данные (экранируется адаптером)."""
    repo = FakeAppRepo({7: _app_in_interview(7)})
    rec = RecorderSpy()
    llm = FakeLlm(recorder=rec, model="fake/hr", response_factory=stub_hr_response)

    await _make(repo=repo, llm=llm).run(7, message_text="Собес 2026-08-20 https://x.io/y")

    data_msg = next(m for m in llm.sent_messages if m["role"] == "user")
    assert "не инструкции" in data_msg["content"]
    system_msg = next(m for m in llm.sent_messages if m["role"] == "system")
    assert system_msg["content"] == SYSTEM


async def test_c_u5_missing_application_is_soft_not_found() -> None:
    repo = FakeAppRepo()
    rec = RecorderSpy()
    llm = FakeLlm(recorder=rec, model="fake/hr", response_factory=stub_hr_response)

    result = await _make(repo=repo, llm=llm).run(999, message_text="Собес 2026-08-20 https://x/y")

    assert result.status == "not_found"
    assert repo.save_calls == 0


async def test_c_u5_empty_extraction_falls_back_to_manual() -> None:
    """Ничего не извлечено (нет даты/ссылки/сути) → мягкий фолбэк на ручной ввод."""
    repo = FakeAppRepo({7: _app_in_interview(7)})
    rec = RecorderSpy()
    empty = json.dumps({"date": None, "url": None, "gist": ""})
    llm = FakeLlm(recorder=rec, model="fake/hr", responses=[empty])

    result = await _make(repo=repo, llm=llm).run(7, message_text="просто привет")

    assert result.status == "empty"
    assert repo.save_calls == 0  # заявка не тронута
    # даже пустое извлечение — вызов учтён (O1)
    assert len(rec.records) == 1


async def test_c_u5_invalid_llm_after_retry_falls_back() -> None:
    """Невалидный вывод → 1 retry (R2) → graceful фолбэк на ручной ввод."""
    repo = FakeAppRepo({7: _app_in_interview(7)})
    rec = RecorderSpy()
    llm = FakeLlm(recorder=rec, model="fake/hr", responses=["мусор", "тоже мусор"])

    result = await _make(repo=repo, llm=llm).run(7, message_text="Собес завтра")

    assert result.status == "llm_failed"
    assert repo.save_calls == 0
    assert llm.attempts == 2  # ровно один валидационный retry (R2)
    assert len(rec.records) == 1  # даже при сбое вызов учтён (O1)


async def test_c_u5_body_not_logged() -> None:
    """M4: тело HR-сообщения (и извлечённая суть) не попадают в логи, только метаданные."""
    import structlog

    repo = FakeAppRepo({7: _app_in_interview(7)})
    rec = RecorderSpy()
    llm = FakeLlm(recorder=rec, model="fake/hr", response_factory=stub_hr_response)
    secret = "СЕКРЕТНЫЙ-ТЕЛЕФОН-8-900-000"
    msg = f"Собес 2026-08-20 https://meet.example/abc — {secret}"

    with structlog.testing.capture_logs() as logs:
        await _make(repo=repo, llm=llm).run(7, message_text=msg)

    assert logs, "use case должен логировать хотя бы метаданные (наблюдаемость)"
    blob = json.dumps(logs, ensure_ascii=False, default=str)
    assert secret not in blob  # тело сообщения не утекло
    assert msg not in blob
    # метаданные присутствуют (событие извлечения зафиксировано)
    assert any(entry.get("vacancy_id") == 7 for entry in logs)
