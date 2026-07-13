"""[T210] Контракт GmailInbox на golden-ответах: маппинг в RawEmail,
401 → refresh → повтор ровно 1 раз (паттерн [S-C2]), body из text/plain part.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import respx

from app.adapters.gmail.auth import GOOGLE_TOKEN_URL
from app.adapters.gmail.source import GmailInbox

GOLDEN = Path(__file__).parent.parent / "golden" / "gmail"
API = "https://gmail.googleapis.com/gmail/v1"


def golden(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((GOLDEN / name).read_text())


def make_inbox() -> GmailInbox:
    return GmailInbox(client_id="cid", client_secret="cs", refresh_token="1//rt")


SINCE = datetime.now(UTC) - timedelta(hours=24)


@respx.mock
async def test_fetch_maps_golden_to_raw_email() -> None:
    respx.post(GOOGLE_TOKEN_URL).mock(
        return_value=httpx.Response(200, json=golden("token_refresh.json"))
    )
    listing = golden("messages_list.json")
    respx.get(f"{API}/users/me/messages").mock(return_value=httpx.Response(200, json=listing))
    message = golden("message_full.json")
    respx.get(url__regex=rf"{API}/users/me/messages/[0-9a-f]+").mock(
        return_value=httpx.Response(200, json=message)
    )

    emails = await make_inbox().fetch_since(SINCE)

    assert len(emails) == len(listing["messages"])
    first = emails[0]
    assert first.sender == "Anna Recruiter <anna.recruiter@example-corp.io>"
    assert first.subject == "Приглашение на интервью — Engineering Manager"
    assert "интервью" in first.body_text  # text/plain part, base64url декодирован
    assert first.url.startswith("https://mail.google.com/mail/u/0/#inbox/")
    assert first.received_at.tzinfo is not None


@respx.mock
async def test_401_refresh_and_retry_exactly_once() -> None:
    token_route = respx.post(GOOGLE_TOKEN_URL).mock(
        return_value=httpx.Response(200, json=golden("token_refresh.json"))
    )
    list_route = respx.get(f"{API}/users/me/messages").mock(
        side_effect=[
            httpx.Response(401, json={"error": {"code": 401}}),
            httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0}),
        ]
    )

    emails = await make_inbox().fetch_since(SINCE)

    assert emails == []
    assert list_route.call_count == 2  # 401 → refresh → ровно один повтор
    assert token_route.call_count == 2  # стартовый access + после 401


@respx.mock
async def test_second_401_raises() -> None:
    respx.post(GOOGLE_TOKEN_URL).mock(
        return_value=httpx.Response(200, json=golden("token_refresh.json"))
    )
    respx.get(f"{API}/users/me/messages").mock(
        return_value=httpx.Response(401, json={"error": {"code": 401}})
    )

    try:
        await make_inbox().fetch_since(SINCE)
        raise AssertionError("ожидали ошибку после второго 401")
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 401


@respx.mock
async def test_empty_inbox_returns_empty_list() -> None:
    respx.post(GOOGLE_TOKEN_URL).mock(
        return_value=httpx.Response(200, json=golden("token_refresh.json"))
    )
    respx.get(f"{API}/users/me/messages").mock(
        return_value=httpx.Response(200, json={"resultSizeEstimate": 0})
    )

    assert await make_inbox().fetch_since(SINCE) == []
