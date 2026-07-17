"""CLI-хелпер ручного входа в браузер-профиль HH (Playwright, headful).

    uv run python -m app.cli.hh_login

Открывает видимый Chromium с сохранённым профилем; владелец входит на hh.ru
руками (и решает капчу, если появится — автоматически НЕ обходим, S5/constitution IV).
После входа профиль (куки) сохраняется в HH_WEB_PROFILE_DIR и переиспользуется
скрейпером. Логин/пароль вводит владелец в браузере — код их не касается.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright

from app.cli._env import read_env_var


async def main() -> None:
    profile_dir = read_env_var("HH_WEB_PROFILE_DIR") or "deploy/hh_profile"
    print("=== JobPilot: вход в браузер-профиль HH (ручной) ===\n")
    print(f"Профиль: {profile_dir}")
    print("Откроется браузер. Войдите на hh.ru, дождитесь ленты рекомендаций,")
    print("затем вернитесь сюда и нажмите Enter — профиль сохранится.\n")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(profile_dir, headless=False)
        page = await context.new_page()
        await page.goto("https://hh.ru/account/login")
        await asyncio.get_event_loop().run_in_executor(None, input, "Готово? Enter для выхода… ")
        await context.close()

    print(f"\n✅ Профиль сохранён: {profile_dir}. GMAIL/HH_MODE=auto подхватит web-источник.")


if __name__ == "__main__":
    asyncio.run(main())
