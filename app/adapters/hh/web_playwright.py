"""Playwright-загрузчик DOM по авторизованной сессии (тонкий I/O, вне CI).

Открывает страницу в persistent-контексте (сохранённый профиль = куки логина),
пауза перед возвратом HTML (1 rps), честный User-Agent. Разбор HTML — в web_source.
"""

from __future__ import annotations

import asyncio

import structlog
from playwright.async_api import async_playwright

log = structlog.get_logger("adapters.hh.web_playwright")


class PlaywrightLoader:
    def __init__(self, *, profile_dir: str, user_agent: str, pause_sec: float = 1.0) -> None:
        self._profile_dir = profile_dir
        self._user_agent = user_agent
        self._pause_sec = pause_sec

    async def load(self, url: str) -> str:
        async with async_playwright() as pw:
            context = await pw.chromium.launch_persistent_context(
                self._profile_dir,
                headless=True,
                user_agent=self._user_agent,
            )
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(self._pause_sec)  # честный rate limit ([S-C10])
                html: str = await page.content()
                return html
            finally:
                await context.close()
