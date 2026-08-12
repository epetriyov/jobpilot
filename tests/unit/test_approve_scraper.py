"""[T507][US3] /approve_scraper: чистые хелперы одобрения + тонкий бот-хендлер.

Неизвестный сайт → вежливый отказ со списком доступных; известный → одобрение.
Персист — интеграционный тест; здесь — логика выбора и рендер ответа.
"""

from __future__ import annotations

from app.bot.handlers import cmd_approve_scraper
from app.config import KNOWN_SITES
from app.runtime.approval import ApprovalOutcome, available_scrapers, is_known_site


class TestPureHelpers:
    def test_known_site(self) -> None:
        assert is_known_site("yandex")
        assert not is_known_site("linkedin")

    def test_available_lists_configured_canary_and_active(self) -> None:
        assert available_scrapers(canary=["yandex", "vk"], active=["sber"]) == [
            "sber",
            "vk",
            "yandex",
        ]

    def test_available_falls_back_to_known_when_none_configured(self) -> None:
        assert available_scrapers(canary=[], active=[]) == sorted(KNOWN_SITES)


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def answer(self, text: str) -> None:
        self.replies.append(text)


class FakeServices:
    def __init__(self, outcome: ApprovalOutcome, available: list[str]) -> None:
        self._outcome = outcome
        self._available = available
        self.calls: list[str] = []

    async def approve_scraper(self, site: str) -> tuple[ApprovalOutcome, list[str]]:
        self.calls.append(site)
        return self._outcome, self._available


class TestHandler:
    async def test_approves_known_site(self) -> None:
        msg = FakeMessage("/approve_scraper yandex")
        services = FakeServices("approved", [])
        await cmd_approve_scraper(msg, services)  # type: ignore[arg-type]
        assert services.calls == ["yandex"]
        assert "yandex" in msg.replies[0]

    async def test_unknown_site_lists_available(self) -> None:
        msg = FakeMessage("/approve_scraper linkedin")
        services = FakeServices("unknown", ["yandex", "vk"])
        await cmd_approve_scraper(msg, services)  # type: ignore[arg-type]
        reply = msg.replies[0]
        assert "yandex" in reply and "vk" in reply

    async def test_missing_arg_asks_for_site(self) -> None:
        msg = FakeMessage("/approve_scraper")
        services = FakeServices("approved", [])
        await cmd_approve_scraper(msg, services)  # type: ignore[arg-type]
        assert services.calls == []  # без аргумента use case не дёргается
        assert msg.replies

    async def test_already_approved_is_idempotent_reply(self) -> None:
        msg = FakeMessage("/approve_scraper vk")
        services = FakeServices("already", [])
        await cmd_approve_scraper(msg, services)  # type: ignore[arg-type]
        assert "vk" in msg.replies[0]
