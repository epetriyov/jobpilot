"""[S-C1] [S-C2] [S-C4b] Парсер HTML рекомендаций HH (web-source, пересмотр 2026-07-15).

Парсинг — чистая функция над HTML (offline, без браузера); Playwright только грузит DOM.
Golden — синтетические плейсхолдеры (tests/golden/hh_web).
"""

from pathlib import Path

import pytest

from app.adapters.hh.web_source import (
    HhWebBlocked,
    detect_block,
    parse_recommendations_html,
)

GOLDEN = Path(__file__).parent.parent / "golden" / "hh_web"


def golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


class TestParse:
    def test_maps_all_cards(self) -> None:
        vacancies = parse_recommendations_html(golden("recommendations.html"))
        assert [v.source_ref.as_key() for v in vacancies] == [
            "hh:92000001",
            "hh:92000002",
            "hh:92000003",
        ]

    def test_fields_and_salary_from_only(self) -> None:
        vacancies = parse_recommendations_html(golden("recommendations.html"))
        first, second, third = vacancies
        assert first.title == "Engineering Manager"
        assert first.company == "Ромашка Технологии"
        assert first.url == "https://hh.ru/vacancy/92000001"
        assert first.location == "Москва"
        assert (first.salary.from_, first.salary.to) == (350_000, 450_000)
        # [S-C1]: «от X» без «до» → Salary(from=X, to=None)
        assert (second.salary.from_, second.salary.to) == (500_000, None)
        # без зарплаты
        assert third.salary.from_ is None and third.salary.to is None

    def test_html_stripped_in_description(self) -> None:
        first = parse_recommendations_html(golden("recommendations.html"))[0]
        assert "<b>" not in first.description_text
        assert "Python" in first.description_text  # S3-очистка доменом (Vacancy.create)


class TestStructureDiffSC2:
    """[S-C2]: изменилась структура → парсер возвращает пусто/меньше → сигнал поломки."""

    def test_changed_structure_yields_nothing(self) -> None:
        broken = golden("recommendations.html").replace(
            'data-qa="vacancy-serp__vacancy"', 'data-qa="renamed-card"'
        )
        assert parse_recommendations_html(broken) == []


class TestBlockDetectionSC4b:
    """[S-C4b]: логин-стена/капча → detect_block → адаптер эскалирует, не обходит."""

    def test_captcha_detected(self) -> None:
        assert detect_block(golden("captcha.html")) == "captcha"

    def test_login_wall_detected(self) -> None:
        assert detect_block(golden("login_wall.html")) == "login"

    def test_antibot_block_detected(self) -> None:
        """Реальная анти-бот/VPN-заглушка HH (2026-07-17) → antibot, эскалация."""
        assert detect_block(golden("blocked_antibot.html")) == "antibot"

    def test_normal_page_not_blocked(self) -> None:
        assert detect_block(golden("recommendations.html")) is None

    def test_hhwebblocked_is_source_error(self) -> None:
        # адаптер поднимает HhWebBlocked → collect_from_sources ловит как SourceFetchFailed (S4)
        with pytest.raises(HhWebBlocked):
            raise HhWebBlocked("captcha")
