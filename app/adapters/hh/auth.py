"""OAuth HH: обмен кода, refresh access token (contracts/hh-api.md, [S-C2]).

Значения токенов никогда не логируются (санитайзер + [X-U1]).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict

AUTHORIZE_URL = "https://hh.ru/oauth/authorize"
TOKEN_URL = "https://api.hh.ru/token"
API_BASE = "https://api.hh.ru"


class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    expires_in: int


def build_authorize_url(client_id: str) -> str:
    return f"{AUTHORIZE_URL}?response_type=code&client_id={client_id}"


async def _post_token(form: dict[str, str], http: httpx.AsyncClient | None = None) -> TokenPair:
    async with http or httpx.AsyncClient(timeout=30) as client:
        response = await client.post(TOKEN_URL, data=form)
        response.raise_for_status()
        payload = response.json()
    return TokenPair(
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
        expires_in=int(payload.get("expires_in", 0)),
    )


async def exchange_code(
    *, client_id: str, client_secret: str, code: str, http: httpx.AsyncClient | None = None
) -> TokenPair:
    """Обмен authorization code на пару токенов (шаг CLI-хелпера)."""
    return await _post_token(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        http,
    )


async def refresh_access_token(
    *, refresh_token: str, http: httpx.AsyncClient | None = None
) -> TokenPair:
    """Обновление протухшего access token ([S-C2]); HH ротирует и refresh token."""
    return await _post_token({"grant_type": "refresh_token", "refresh_token": refresh_token}, http)
