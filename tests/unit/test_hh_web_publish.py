"""[S-C3] Поднятие резюме через web (Playwright-клик, пересмотр 2026-07-15).

Определение состояния — чистая функция на golden HTML; клик — тонкий actor.
DRY_RUN обрабатывается выше (PublishResume), здесь — сам адаптер.
"""

from pathlib import Path

from app.adapters.hh.web_publish import HhWebPublisher, detect_publish_state

GOLDEN = Path(__file__).parent.parent / "golden" / "hh_web"


def golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


class TestDetectState:
    def test_ready(self) -> None:
        assert detect_publish_state(golden("resume_ready.html")) == "ready"

    def test_limit(self) -> None:
        assert detect_publish_state(golden("resume_limit.html")) == "limit"


class FakeActor:
    """Грузит golden HTML и считает клики (вместо Playwright)."""

    def __init__(self, html: str) -> None:
        self._html = html
        self.clicks = 0

    async def load(self, url: str) -> str:
        return self._html

    async def click_publish(self, url: str) -> None:
        self.clicks += 1


class TestPublisher:
    async def test_ready_publishes(self) -> None:
        actor = FakeActor(golden("resume_ready.html"))
        publisher = HhWebPublisher(actor=actor, resume_url="https://hh.ru/resume/abc")

        outcome = await publisher.publish()

        assert outcome == "published"
        assert actor.clicks == 1

    async def test_limit_skips_without_click(self) -> None:
        """[S-C3]: лимит → skipped_limit, без клика, без ретрая."""
        actor = FakeActor(golden("resume_limit.html"))
        publisher = HhWebPublisher(actor=actor, resume_url="https://hh.ru/resume/abc")

        outcome = await publisher.publish()

        assert outcome == "skipped_limit"
        assert actor.clicks == 0
