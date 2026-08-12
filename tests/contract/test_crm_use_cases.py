"""Contract-тесты use cases CRM (спека 006, US2/US3) на in-memory фейках репозиториев.

Кейсы: [C-U4] 💾 создаёт Application(new)+VacancySaved, повтор не плодит дубль (C1);
переходы/раунды/отказ/удаление через доменные методы; недопустимое → «illegal»
без изменения состояния (C2); [C-U5] «➕ собес» дополняет детали, статус не меняет (C3).
"""

from __future__ import annotations

import pytest

from app.application.add_interview_details import AddInterviewDetails
from app.application.change_status import ChangeApplicationStatus
from app.application.save_vacancy import SaveVacancy
from app.domain.crm import (
    Application,
    ApplicationStatus,
    InterviewRoundKind,
    RejectStage,
    VacancySaved,
)
from app.ports.repositories import VacancyRecord


class FakeVacancyRepo:
    def __init__(self, ids: set[int]) -> None:
        self._ids = ids

    async def get_by_id(self, vacancy_id: int) -> VacancyRecord | None:
        if vacancy_id not in self._ids:
            return None
        from datetime import UTC, datetime

        from app.domain.shared import Source, SourceRef

        return VacancyRecord(
            id=vacancy_id,
            source_ref=SourceRef(source=Source.HH, external_id=str(vacancy_id)),
            title="EM",
            company="Acme",
            url="u",
            description_text="",
            first_seen_at=datetime.now(UTC),
        )


class FakeAppRepo:
    def __init__(self) -> None:
        self._by_vacancy: dict[int, Application] = {}
        self.save_calls = 0

    async def get_by_vacancy(self, vacancy_id: int) -> Application | None:
        app = self._by_vacancy.get(vacancy_id)
        return app.model_copy(deep=True) if app else None  # снапшот: мутации не «утекают»

    async def save(self, app: Application) -> int:
        self.save_calls += 1
        self._by_vacancy[app.vacancy_id] = app.model_copy(deep=True)
        return app.vacancy_id

    async def delete(self, vacancy_id: int) -> None:
        self._by_vacancy.pop(vacancy_id, None)

    async def list_all(self) -> list[Application]:
        return list(self._by_vacancy.values())

    async def funnel_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for app in self._by_vacancy.values():
            counts[str(app.status)] = counts.get(str(app.status), 0) + 1
        return counts


class TestSaveVacancyCU4:
    async def test_save_creates_new_and_emits_event(self) -> None:
        apps = FakeAppRepo()
        uc = SaveVacancy(apps=apps, vacancies=FakeVacancyRepo({7}))

        outcome, event = await uc.run(7)

        assert outcome == "saved"
        assert isinstance(event, VacancySaved) and event.vacancy_id == 7
        saved = await apps.get_by_vacancy(7)
        assert saved is not None and saved.status is ApplicationStatus.NEW

    async def test_repeat_save_does_not_duplicate(self) -> None:
        apps = FakeAppRepo()
        uc = SaveVacancy(apps=apps, vacancies=FakeVacancyRepo({7}))
        await uc.run(7)
        before = apps.save_calls

        outcome, event = await uc.run(7)

        assert outcome == "already"
        assert event is None
        assert apps.save_calls == before  # C1: второй save не выполнялся

    async def test_save_unknown_vacancy_not_found(self) -> None:
        uc = SaveVacancy(apps=FakeAppRepo(), vacancies=FakeVacancyRepo(set()))
        outcome, event = await uc.run(999)
        assert outcome == "not_found" and event is None


class TestChangeStatus:
    async def _saved(self, vacancy_id: int = 7) -> FakeAppRepo:
        apps = FakeAppRepo()
        await SaveVacancy(apps=apps, vacancies=FakeVacancyRepo({vacancy_id})).run(vacancy_id)
        return apps

    async def test_full_forward_cycle(self) -> None:
        apps = await self._saved()
        uc = ChangeApplicationStatus(apps=apps)

        assert await uc.advance(7, ApplicationStatus.APPLIED) == "ok"
        assert await uc.advance(7, ApplicationStatus.INTERVIEW) == "ok"
        assert await uc.add_round(7, InterviewRoundKind.HR) == "ok"
        assert await uc.add_round(7, InterviewRoundKind.TECH_1) == "ok"
        assert await uc.advance(7, ApplicationStatus.OFFER) == "ok"

        app = await apps.get_by_vacancy(7)
        assert app is not None and app.status is ApplicationStatus.OFFER
        assert [r.kind for r in app.interview_rounds] == [
            InterviewRoundKind.HR,
            InterviewRoundKind.TECH_1,
        ]

    async def test_illegal_transition_keeps_state(self) -> None:
        apps = await self._saved()
        uc = ChangeApplicationStatus(apps=apps)
        # new → interview (мимо applied) недопустим (C2)
        assert await uc.advance(7, ApplicationStatus.INTERVIEW) == "illegal"
        app = await apps.get_by_vacancy(7)
        assert app is not None and app.status is ApplicationStatus.NEW

    async def test_round_out_of_interview_illegal(self) -> None:
        apps = await self._saved()
        uc = ChangeApplicationStatus(apps=apps)
        assert await uc.add_round(7, InterviewRoundKind.HR) == "illegal"

    async def test_reject_valid_and_invalid_stage(self) -> None:
        apps = await self._saved()
        uc = ChangeApplicationStatus(apps=apps)
        await uc.advance(7, ApplicationStatus.APPLIED)
        # из applied tech недопустим
        assert await uc.reject(7, RejectStage.TECH) == "illegal"
        assert await uc.reject(7, RejectStage.HR) == "ok"
        app = await apps.get_by_vacancy(7)
        assert app is not None and app.status is ApplicationStatus.REJECTED
        assert app.reject_stage is RejectStage.HR

    async def test_reject_without_stage_illegal(self) -> None:
        apps = await self._saved()
        uc = ChangeApplicationStatus(apps=apps)
        assert await uc.reject(7, None) == "illegal"

    async def test_delete_frees_vacancy_for_resave(self) -> None:
        apps = await self._saved()
        uc = ChangeApplicationStatus(apps=apps)
        assert await uc.delete(7) == "deleted"
        assert await apps.get_by_vacancy(7) is None
        # повторное 💾 создаёт новый Application (C1: прежний удалён)
        outcome, _ = await SaveVacancy(apps=apps, vacancies=FakeVacancyRepo({7})).run(7)
        assert outcome == "saved"

    async def test_actions_on_missing_application(self) -> None:
        uc = ChangeApplicationStatus(apps=FakeAppRepo())
        assert await uc.advance(1, ApplicationStatus.APPLIED) == "not_found"
        assert await uc.add_round(1, InterviewRoundKind.HR) == "not_found"
        assert await uc.reject(1, RejectStage.HR) == "not_found"
        assert await uc.delete(1) == "not_found"


class TestAddInterviewDetailsCU5:
    async def test_details_do_not_change_status(self) -> None:
        apps = FakeAppRepo()
        await SaveVacancy(apps=apps, vacancies=FakeVacancyRepo({7})).run(7)
        await ChangeApplicationStatus(apps=apps).advance(7, ApplicationStatus.APPLIED)

        outcome = await AddInterviewDetails(apps=apps).run(
            7, url="https://meet.example/abc", notes="в 15:00 МСК"
        )

        assert outcome == "ok"
        app = await apps.get_by_vacancy(7)
        assert app is not None
        assert app.status is ApplicationStatus.APPLIED  # C3: статус не тронут
        assert app.interview_url == "https://meet.example/abc"
        assert app.notes is not None and "15:00" in app.notes

    async def test_details_on_missing_application(self) -> None:
        outcome = await AddInterviewDetails(apps=FakeAppRepo()).run(1, url="u")
        assert outcome == "not_found"


@pytest.mark.parametrize("vacancy_id", [1, 42, 100500])
async def test_save_various_ids(vacancy_id: int) -> None:
    apps = FakeAppRepo()
    outcome, _ = await SaveVacancy(apps=apps, vacancies=FakeVacancyRepo({vacancy_id})).run(
        vacancy_id
    )
    assert outcome == "saved"
