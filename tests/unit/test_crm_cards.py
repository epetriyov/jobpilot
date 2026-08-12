"""Клавиатуры/колбэки CRM: формат callback_data ≤64, разбор, контекстные кнопки."""

from __future__ import annotations

import pytest

from app.adapters.telegram.crm_cards import (
    CrmCallback,
    SavedApplicationView,
    build_save_button,
    build_saved_keyboard,
    parse_crm_callback,
    render_saved_text,
)


class TestParse:
    def test_save(self) -> None:
        assert parse_crm_callback("crm:save:42") == CrmCallback(
            action="save", arg=None, vacancy_id=42
        )

    def test_advance(self) -> None:
        assert parse_crm_callback("crm:adv:applied:7") == CrmCallback(
            action="adv", arg="applied", vacancy_id=7
        )

    def test_round(self) -> None:
        assert parse_crm_callback("crm:rnd:tech-1:7") == CrmCallback(
            action="rnd", arg="tech-1", vacancy_id=7
        )

    def test_reject(self) -> None:
        assert parse_crm_callback("crm:rej:pre_hr:7") == CrmCallback(
            action="rej", arg="pre_hr", vacancy_id=7
        )

    def test_delete_and_iv(self) -> None:
        assert parse_crm_callback("crm:del:7").action == "del"
        assert parse_crm_callback("crm:iv:7").action == "iv"

    def test_garbage_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_crm_callback("noise:1")
        with pytest.raises(ValueError):
            parse_crm_callback("crm:bogus:1")


def _view(status: str, rounds: list[str] | None = None) -> SavedApplicationView:
    return SavedApplicationView(
        vacancy_id=7,
        title="Engineering Manager",
        company="Acme",
        status=status,
        rounds=rounds or [],
        interview_url=None,
        notes=None,
    )


class TestKeyboards:
    def test_save_button_roundtrips(self) -> None:
        btn = build_save_button(42)
        assert btn.callback_data == "crm:save:42"

    def test_all_callback_data_fit_limit(self) -> None:
        for status in ("new", "applied", "interview", "offer", "rejected"):
            kb = build_saved_keyboard(_view(status, rounds=["hr"]))
            for row in kb.inline_keyboard:
                for btn in row:
                    if btn.callback_data:
                        assert len(btn.callback_data.encode()) <= 64

    def test_new_has_advance_and_delete(self) -> None:
        datas = _flatten(build_saved_keyboard(_view("new")))
        assert "crm:adv:applied:7" in datas
        assert "crm:del:7" in datas

    def test_interview_offers_next_round_and_offer(self) -> None:
        datas = _flatten(build_saved_keyboard(_view("interview", rounds=["hr"])))
        assert "crm:rnd:tech-1:7" in datas  # следующий раунд после hr
        assert "crm:rnd:hr:7" not in datas  # уже пройден — не предлагаем
        assert "crm:adv:offer:7" in datas
        assert "crm:iv:7" in datas

    def test_reject_stages_depend_on_status(self) -> None:
        applied = _flatten(build_saved_keyboard(_view("applied")))
        assert "crm:rej:pre_hr:7" in applied and "crm:rej:hr:7" in applied
        assert "crm:rej:tech:7" not in applied
        interview = _flatten(build_saved_keyboard(_view("interview", rounds=["hr"])))
        assert "crm:rej:tech:7" in interview and "crm:rej:final:7" in interview

    def test_terminal_only_delete(self) -> None:
        for status in ("offer", "rejected"):
            datas = _flatten(build_saved_keyboard(_view(status)))
            assert datas == ["crm:del:7"]

    def test_render_text_has_fields(self) -> None:
        text = render_saved_text(_view("interview", rounds=["hr", "tech-1"]))
        assert "Engineering Manager" in text
        assert "Acme" in text
        assert "hr" in text and "tech-1" in text


def _flatten(kb: object) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard  # type: ignore[attr-defined]
        for btn in row
        if btn.callback_data
    ]
