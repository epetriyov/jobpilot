"""Playwright-actor страницы резюме HH (тонкий I/O, вне CI).

Грузит резюме по сохранённому профилю и жмёт «Поднять». Определение состояния
(доступно/лимит) — в web_publish (чистая функция на HTML).
"""

from __future__ import annotations

import structlog
from playwright.async_api import async_playwright

log = structlog.get_logger("adapters.hh.resume_playwright")

_PUBLISH_BUTTON = '[data-qa="resume-update-button"]'


class PlaywrightResumeActor:
    def __init__(self, *, profile_dir: str, user_agent: str) -> None:
        self._profile_dir = profile_dir
        self._user_agent = user_agent

    async def _context(self, pw: object):  # type: ignore[no-untyped-def]
        return await pw.chromium.launch_persistent_context(  # type: ignore[attr-defined]
            self._profile_dir, headless=True, user_agent=self._user_agent
        )

    async def load(self, url: str) -> str:
        async with async_playwright() as pw:
            context = await self._context(pw)
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                html: str = await page.content()
                return html
            finally:
                await context.close()

    async def click_publish(self, url: str) -> None:
        async with async_playwright() as pw:
            context = await self._context(pw)
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                await page.click(_PUBLISH_BUTTON)
                log.info("resume_publish_clicked")
            finally:
                await context.close()
