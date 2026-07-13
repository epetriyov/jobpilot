"""Контракт OAuth HH (T118, база для [S-C2]): обмен кода и refresh на respx."""

import httpx
import pytest
import respx

from app.adapters.hh.auth import TOKEN_URL, TokenPair, exchange_code, refresh_access_token

TOKENS_JSON = {
    "access_token": "hh-access-abc",
    "refresh_token": "hh-refresh-xyz",
    "token_type": "bearer",
    "expires_in": 1209600,
}


@respx.mock
async def test_exchange_code_posts_form_and_returns_tokens() -> None:
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKENS_JSON))

    pair = await exchange_code(client_id="cid", client_secret="csecret", code="auth-code-1")

    assert pair == TokenPair(
        access_token="hh-access-abc", refresh_token="hh-refresh-xyz", expires_in=1209600
    )
    form = dict(
        pair_str.split("=", 1) for pair_str in route.calls[0].request.content.decode().split("&")
    )
    assert form["grant_type"] == "authorization_code"
    assert form["client_id"] == "cid"
    assert form["client_secret"] == "csecret"
    assert form["code"] == "auth-code-1"


@respx.mock
async def test_refresh_returns_new_pair() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKENS_JSON))

    pair = await refresh_access_token(refresh_token="old-refresh")

    assert pair.access_token == "hh-access-abc"
    assert pair.refresh_token == "hh-refresh-xyz"


@respx.mock
async def test_exchange_error_raises() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))

    with pytest.raises(httpx.HTTPStatusError):
        await exchange_code(client_id="cid", client_secret="cs", code="bad")
