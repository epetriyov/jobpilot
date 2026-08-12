"""T6E-4: карточка сопроводительного письма — кнопки 🔁/✏️, ✉️-вход, парсинг колбэка."""

import pytest

from app.adapters.telegram.cards import (
    build_cover_entry_button,
    build_cover_keyboard,
    parse_cover_callback,
    render_cover_text,
)
from app.ports.notifier import CoverLetterCard

CARD = CoverLetterCard(vacancy_id=42, title="Head of Engineering", company="Ромашка", text="Письмо")


def test_entry_button_triggers_generation() -> None:
    button = build_cover_entry_button(42)
    assert button.callback_data == "cover:new:42"
    assert "письмо" in button.text


def test_keyboard_has_regenerate_and_edit() -> None:
    kb = build_cover_keyboard(CARD)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "cover:regen:42" in datas  # 🔁 перегенерировать
    assert "cover:edit:42" in datas  # ✏️ править


def test_render_shows_manual_send_hint_and_text() -> None:
    text = render_cover_text(CARD)
    assert "вручную" in text  # отправку делает человек (M3/VI)
    assert "Письмо" in text


def test_parse_cover_callback_ok() -> None:
    assert parse_cover_callback("cover:regen:7") == ("regen", 7)
    assert parse_cover_callback("cover:new:1") == ("new", 1)
    assert parse_cover_callback("cover:edit:99") == ("edit", 99)


def test_parse_cover_callback_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_cover_callback("label:relevant:hh:1")
    with pytest.raises(ValueError):
        parse_cover_callback("cover:send:1")  # отправки нет — только new/regen/edit
