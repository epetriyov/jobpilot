"""HhWebPublisher — поднятие резюме кликом «Поднять» через Playwright (пересмотр 2026-07-15).

Определение состояния резюме — чистая функция на HTML (offline-тесты);
клик — тонкий actor (Playwright). Лимит «ещё рано» → skipped_limit без ретрая ([S-C3]).
DRY_RUN обрабатывается use case'ом PublishResume (клик сюда не доходит).
"""

from __future__ import annotations

from typing import Literal, Protocol

import structlog

from app.ports.notifier import PublishOutcome

log = structlog.get_logger("adapters.hh.web_publish")

_READY_MARKER = 'data-qa="resume-update-button"'
_LIMIT_MARKERS = ("поднять можно через", "buttonenabled_false")


def detect_publish_state(html: str) -> Literal["ready", "limit"]:
    lowered = html.lower()
    if any(m in lowered for m in _LIMIT_MARKERS):
        return "limit"
    if _READY_MARKER.lower() in lowered:
        return "ready"
    return "limit"  # неизвестно → считаем недоступным (не жмём вслепую)


class ResumePageActor(Protocol):
    async def load(self, url: str) -> str: ...

    async def click_publish(self, url: str) -> None: ...


class HhWebPublisher:
    """PublisherPort: грузит страницу резюме, жмёт «поднять», если доступно."""

    def __init__(self, *, actor: ResumePageActor, resume_url: str) -> None:
        self._actor = actor
        self._resume_url = resume_url

    async def publish(self) -> PublishOutcome:
        html = await self._actor.load(self._resume_url)
        state = detect_publish_state(html)
        if state == "limit":
            log.info("resume_publish_limit")  # [S-C3]: штатный skip, без ретрая
            return "skipped_limit"
        await self._actor.click_publish(self._resume_url)
        log.info("resume_published")
        return "published"
