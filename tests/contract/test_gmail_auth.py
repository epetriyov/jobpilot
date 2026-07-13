"""Контракт OAuth Google (T211): обмен кода и refresh на respx, токены не логируются."""

import httpx
import pytest
import respx

from app.adapters.gmail.auth import (
    GOOGLE_TOKEN_URL,
    GoogleTokens,
    build_authorize_url,
    exchange_code,
    refresh_access_token,
)

TOKENS_JSON = {
    "access_token": "ya29.google-access",
    "refresh_token": "1//google-refresh",
    "expires_in": 3599,
    "scope": "https://www.googleapis.com/auth/gmail.readonly",
    "token_type": "Bearer",
}


def test_authorize_url_has_offline_access_and_readonly_scope() -> None:
    url = build_authorize_url(client_id="cid", redirect_uri="http://127.0.0.1:8765/")
    assert "access_type=offline" in url  # иначе Google не выдаст refresh token
    assert "prompt=consent" in url
    assert "gmail.readonly" in url
    assert "client_id=cid" in url


@respx.mock
async def test_exchange_code_posts_form_and_returns_tokens() -> None:
    route = respx.post(GOOGLE_TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKENS_JSON))

    tokens = await exchange_code(
        client_id="cid",
        client_secret="csecret",
        code="auth-code",
        redirect_uri="http://127.0.0.1:8765/",
    )

    assert tokens == GoogleTokens(
        access_token="ya29.google-access", refresh_token="1//google-refresh", expires_in=3599
    )
    form = dict(pair.split("=", 1) for pair in route.calls[0].request.content.decode().split("&"))
    assert form["grant_type"] == "authorization_code"
    assert form["client_id"] == "cid"
    assert form["code"] == "auth-code"


@respx.mock
async def test_refresh_returns_access_keeps_refresh() -> None:
    """Google при refresh НЕ возвращает refresh_token — сохраняем старый."""
    payload = {k: v for k, v in TOKENS_JSON.items() if k != "refresh_token"}
    respx.post(GOOGLE_TOKEN_URL).mock(return_value=httpx.Response(200, json=payload))

    tokens = await refresh_access_token(
        client_id="cid", client_secret="cs", refresh_token="1//old-refresh"
    )

    assert tokens.access_token == "ya29.google-access"
    assert tokens.refresh_token == "1//old-refresh"  # старый сохранён


@respx.mock
async def test_exchange_error_raises() -> None:
    respx.post(GOOGLE_TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await exchange_code(
            client_id="c", client_secret="s", code="bad", redirect_uri="http://127.0.0.1:8765/"
        )
