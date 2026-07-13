"""CLI-хелпер OAuth HH (T118, quickstart этапа 1 — запускает владелец, один раз).

    uv run python -m app.cli.oauth_hh

Шаги: авторизация в браузере → вставка кода → обмен на refresh token →
выбор резюме → печать строк для .env. Токены в логи/файлы не пишутся —
только вывод в терминал владельца.
"""

from __future__ import annotations

import asyncio
import os

import httpx

from app.adapters.hh.auth import API_BASE, build_authorize_url, exchange_code
from app.cli._env import ask


async def _list_resumes(access_token: str, user_agent: str) -> list[tuple[str, str]]:
    headers = {"Authorization": f"Bearer {access_token}", "HH-User-Agent": user_agent}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        response = await client.get(f"{API_BASE}/resumes/mine")
        response.raise_for_status()
        items = response.json().get("items", [])
    return [(item["id"], item.get("title", "<без названия>")) for item in items]


async def main() -> None:
    print("=== JobPilot: настройка доступа к HH (один раз) ===\n")
    client_id = ask("HH_CLIENT_ID (из dev.hh.ru)", "HH_CLIENT_ID")
    client_secret = ask("HH_CLIENT_SECRET", "HH_CLIENT_SECRET")
    user_agent = os.environ.get("HH_USER_AGENT", "JobPilot/0.1 (jobpilot-owner)")

    print("\n1) Откройте в браузере и подтвердите доступ:")
    print(f"   {build_authorize_url(client_id)}")
    print("2) После подтверждения браузер уйдёт на redirect_uri вашего приложения;")
    print("   скопируйте значение параметра ?code=... из адресной строки.\n")
    code = input("Вставьте code: ").strip()

    tokens = await exchange_code(client_id=client_id, client_secret=client_secret, code=code)
    print("\n✅ Токены получены.")

    try:
        resumes = await _list_resumes(tokens.access_token, user_agent)
    except httpx.HTTPError as exc:
        print(f"⚠️ Не удалось получить список резюме ({exc}); HH_RESUME_ID добавьте вручную.")
        resumes = []

    if resumes:
        print("\nВаши резюме:")
        for resume_id, title in resumes:
            print(f"  {resume_id}  —  {title}")

    print("\nДобавьте в .env (значения показаны только здесь, нигде не сохранены):")
    print(f"HH_CLIENT_ID={client_id}")
    print(f"HH_CLIENT_SECRET={client_secret}")
    print(f"HH_REFRESH_TOKEN={tokens.refresh_token}")
    if resumes:
        print(f"HH_RESUME_ID={resumes[0][0]}   # ← проверьте, что это резюме EM")


if __name__ == "__main__":
    asyncio.run(main())
