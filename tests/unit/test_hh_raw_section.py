"""[S-C4]/S-C6: непарсенные сообщения HH-бота → raw-секция дайджеста (T117)."""

from app.adapters.hh.telegram_source import render_raw_section


def test_render_raw_section() -> None:
    unparsed = ["У вас 3 новых вакансии", "Спасибо, что пользуетесь ботом"]
    text = render_raw_section(unparsed)
    assert text is not None
    assert "HH-бот" in text
    assert "3 новых вакансии" in text


def test_empty_raw_section_is_none() -> None:
    assert render_raw_section([]) is None
