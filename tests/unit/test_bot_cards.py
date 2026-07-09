"""[T111]/[T113] Карточка: клавиатура 👍/👎/🔗 и разбор callback_data."""

import pytest

from app.adapters.telegram.cards import build_card_keyboard, parse_label_callback, render_card_text
from app.ports.notifier import DigestCard

CARD = DigestCard(
    ref_key="hh:42",
    title="Engineering Manager",
    company="Acme",
    url="https://hh.ru/vacancy/42",
    salary_text="от 300 000 RUR",
    score=87,
    reason="сильный матч по стеку",
)


def test_keyboard_has_like_dislike_link() -> None:
    keyboard = build_card_keyboard(CARD)
    buttons = keyboard.inline_keyboard[0]

    assert buttons[0].callback_data == "label:relevant:hh:42"
    assert buttons[1].callback_data == "label:irrelevant:hh:42"
    assert buttons[2].url == "https://hh.ru/vacancy/42"


def test_callback_data_fits_telegram_limit() -> None:
    long_card = CARD.model_copy(update={"ref_key": "hh:" + "9" * 40})
    keyboard = build_card_keyboard(long_card)
    for button in keyboard.inline_keyboard[0]:
        if button.callback_data:
            assert len(button.callback_data.encode()) <= 64


def test_render_card_text_contains_fields() -> None:
    text = render_card_text(CARD)
    assert "Engineering Manager" in text
    assert "Acme" in text
    assert "от 300 000 RUR" in text
    assert "87" in text
    assert "сильный матч" in text


def test_render_without_salary() -> None:
    card = CARD.model_copy(update={"salary_text": None})
    assert "None" not in render_card_text(card)


class TestParseLabelCallback:
    def test_relevant(self) -> None:
        assert parse_label_callback("label:relevant:hh:42") == ("relevant", "hh:42")

    def test_irrelevant_with_site_ref(self) -> None:
        verdict, ref = parse_label_callback("label:irrelevant:site:vk:abc:1")
        assert verdict == "irrelevant"
        assert ref == "site:vk:abc:1"

    def test_garbage_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_label_callback("noise:xxx")
