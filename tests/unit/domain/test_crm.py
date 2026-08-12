"""Домен CRM (DOMAIN.md §3.3): статусная машина Application, раунды, отказ.

Кейсы: [C-U1] переходы только вперёд (property, все пары); [C-U2] раунды строго
по возрастанию только в interview; [C-U3] reject_stage по источнику; [C-U5]
add_interview_details дополняет детали, статус не меняет (C3).
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.crm import (
    Application,
    ApplicationStatus,
    IllegalTransition,
    InterviewRoundKind,
    InterviewScheduled,
    RejectStage,
    StatusChanged,
    VacancySaved,
)

# Единственный источник истины (§3.3): линейные переходы вперёд.
ALLOWED_LINEAR: set[tuple[ApplicationStatus, ApplicationStatus]] = {
    (ApplicationStatus.NEW, ApplicationStatus.APPLIED),
    (ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEW),
    (ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER),
}

STATUSES = list(ApplicationStatus)


def app_in(status: ApplicationStatus) -> Application:
    """Собрать агрегат в произвольном статусе (для перебора пар)."""
    return Application(vacancy_id=1, status=status)


class TestFactory:
    def test_create_starts_new_and_emits_saved(self) -> None:
        app, event = Application.create(vacancy_id=42)
        assert app.status is ApplicationStatus.NEW
        assert app.vacancy_id == 42
        assert isinstance(event, VacancySaved)
        assert event.vacancy_id == 42


class TestStatusPairsCU1:
    """[C-U1] Перебор всех пар (from,to): допустимы только §3.3, иначе IllegalTransition."""

    @given(
        frm=st.sampled_from(STATUSES),
        to=st.sampled_from(STATUSES),
    )
    def test_all_pairs(self, frm: ApplicationStatus, to: ApplicationStatus) -> None:
        app = app_in(frm)
        if (frm, to) in ALLOWED_LINEAR:
            event = app.transition(to)
            assert app.status is to
            assert isinstance(event, StatusChanged)
            assert event.from_status is frm and event.to_status is to
        else:
            with pytest.raises(IllegalTransition):
                app.transition(to)
            assert app.status is frm  # C2: состояние неизменно

    def test_named_methods_follow_linear_path(self) -> None:
        app, _ = Application.create(vacancy_id=1)
        app.apply()
        assert app.status is ApplicationStatus.APPLIED
        app.to_interview()
        assert app.status is ApplicationStatus.INTERVIEW
        app.to_offer()
        assert app.status is ApplicationStatus.OFFER

    def test_apply_from_wrong_state_is_illegal(self) -> None:
        app = app_in(ApplicationStatus.INTERVIEW)
        with pytest.raises(IllegalTransition):
            app.apply()
        assert app.status is ApplicationStatus.INTERVIEW


class TestRoundsCU2:
    """[C-U2] Раунды только в interview, строго по возрастанию; повтор → ошибка."""

    KINDS: ClassVar[list[InterviewRoundKind]] = list(InterviewRoundKind)

    def test_add_round_outside_interview_is_illegal(self) -> None:
        for status in (ApplicationStatus.NEW, ApplicationStatus.APPLIED, ApplicationStatus.OFFER):
            app = app_in(status)
            with pytest.raises(IllegalTransition):
                app.add_round(InterviewRoundKind.HR)
            assert app.interview_rounds == []

    def test_hr_then_tech1_then_tech2_ok(self) -> None:
        app = app_in(ApplicationStatus.INTERVIEW)
        app.add_round(InterviewRoundKind.HR)
        app.add_round(InterviewRoundKind.TECH_1)
        event = app.add_round(InterviewRoundKind.TECH_2)
        assert [r.kind for r in app.interview_rounds] == [
            InterviewRoundKind.HR,
            InterviewRoundKind.TECH_1,
            InterviewRoundKind.TECH_2,
        ]
        assert [r.ordinal for r in app.interview_rounds] == [1, 2, 3]
        assert isinstance(event, InterviewScheduled)
        assert event.kind is InterviewRoundKind.TECH_2

    def test_repeat_hr_is_order_error(self) -> None:
        app = app_in(ApplicationStatus.INTERVIEW)
        app.add_round(InterviewRoundKind.HR)
        with pytest.raises(IllegalTransition):
            app.add_round(InterviewRoundKind.HR)
        assert len(app.interview_rounds) == 1

    def test_repeat_tech1_is_order_error(self) -> None:
        app = app_in(ApplicationStatus.INTERVIEW)
        app.add_round(InterviewRoundKind.HR)
        app.add_round(InterviewRoundKind.TECH_1)
        with pytest.raises(IllegalTransition):
            app.add_round(InterviewRoundKind.TECH_1)
        assert len(app.interview_rounds) == 2

    @given(kinds=st.lists(st.sampled_from(KINDS), min_size=0, max_size=8))
    def test_monotonic_property(self, kinds: list[InterviewRoundKind]) -> None:
        """Любая последовательность: успех ⇔ строго возрастающий ранг; иначе состояние цело."""
        app = app_in(ApplicationStatus.INTERVIEW)
        last_rank = -1
        for kind in kinds:
            rank = InterviewRoundKind.rank(kind)
            before = list(app.interview_rounds)
            before_kinds = [r.kind for r in before]
            if rank > last_rank:
                app.add_round(kind)
                last_rank = rank
                assert [r.kind for r in app.interview_rounds] == [*before_kinds, kind]
                assert app.interview_rounds[-1].ordinal == len(before) + 1
            else:
                with pytest.raises(IllegalTransition):
                    app.add_round(kind)
                assert app.interview_rounds == before


class TestRejectCU3:
    """[C-U3] reject_stage по источнику; stage обязателен."""

    @given(
        frm=st.sampled_from([ApplicationStatus.NEW, ApplicationStatus.APPLIED]),
        stage=st.sampled_from(list(RejectStage)),
    )
    def test_reject_from_new_or_applied(self, frm: ApplicationStatus, stage: RejectStage) -> None:
        app = app_in(frm)
        if stage in {RejectStage.PRE_HR, RejectStage.HR}:
            app.reject(stage)
            assert app.status is ApplicationStatus.REJECTED
            assert app.reject_stage is stage
        else:
            with pytest.raises(IllegalTransition):
                app.reject(stage)
            assert app.status is frm and app.reject_stage is None

    @given(stage=st.sampled_from(list(RejectStage)))
    def test_reject_from_interview(self, stage: RejectStage) -> None:
        app = app_in(ApplicationStatus.INTERVIEW)
        if stage in {RejectStage.HR, RejectStage.TECH, RejectStage.FINAL}:
            app.reject(stage)
            assert app.status is ApplicationStatus.REJECTED
            assert app.reject_stage is stage
        else:
            with pytest.raises(IllegalTransition):
                app.reject(stage)
            assert app.status is ApplicationStatus.INTERVIEW

    def test_reject_without_stage_errors(self) -> None:
        app = app_in(ApplicationStatus.APPLIED)
        with pytest.raises(IllegalTransition):
            app.reject(None)
        assert app.status is ApplicationStatus.APPLIED

    def test_reject_from_terminal_is_illegal(self) -> None:
        for status in (ApplicationStatus.OFFER, ApplicationStatus.REJECTED):
            app = app_in(status)
            with pytest.raises(IllegalTransition):
                app.reject(RejectStage.FINAL)
            assert app.status is status


class TestInterviewDetailsCU5:
    """[C-U5] add_interview_details дополняет url/notes, статус НЕ меняет (C3)."""

    def test_details_do_not_change_status(self) -> None:
        for status in STATUSES:
            app = app_in(status)
            app.add_interview_details(url="https://meet.example/abc", notes="в 15:00")
            assert app.status is status
            assert app.interview_url == "https://meet.example/abc"
            assert app.notes is not None and "15:00" in app.notes

    def test_notes_accumulate(self) -> None:
        app = app_in(ApplicationStatus.INTERVIEW)
        app.add_interview_details(notes="первая заметка")
        app.add_interview_details(notes="вторая заметка")
        assert app.notes is not None
        assert "первая заметка" in app.notes and "вторая заметка" in app.notes
