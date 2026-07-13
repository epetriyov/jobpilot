"""OAuth Google для Gmail (T211, contracts этапа 2): installed-app flow, scope readonly.

Значения токенов не логируются ([X-U1]); refresh token Google выдаёт только
при access_type=offline&prompt=consent и НЕ возвращает при refresh — сохраняем старый.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


class GoogleTokens(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    expires_in: int


def build_authorize_url(*, client_id: str, redirect_uri: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SCOPE,
            "access_type": "offline",  # обязательно: иначе refresh token не выдаётся
            "prompt": "consent",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


async def _post_token(form: dict[str, str], *, keep_refresh: str | None = None) -> GoogleTokens:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=form)
        response.raise_for_status()
        payload = response.json()
    return GoogleTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token") or keep_refresh or "",
        expires_in=int(payload.get("expires_in", 0)),
    )


async def exchange_code(
    *, client_id: str, client_secret: str, code: str, redirect_uri: str
) -> GoogleTokens:
    return await _post_token(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    )


async def refresh_access_token(
    *, client_id: str, client_secret: str, refresh_token: str
) -> GoogleTokens:
    return await _post_token(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        keep_refresh=refresh_token,
    )
