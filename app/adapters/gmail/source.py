"""GmailInbox — реальная реализация InboxPort (T210, contracts этапа 2).

REST Gmail API через httpx; access token в памяти, 401 → refresh → повтор
ровно один раз (паттерн [S-C2]). Тела писем не логируются (M4).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.adapters.gmail.auth import GMAIL_API_BASE, refresh_access_token
from app.ports.inbox import RawEmail

log = structlog.get_logger("adapters.gmail")

MAX_MESSAGES = 50


class GmailInbox:
    name = "gmail"

    def __init__(self, *, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None

    async def fetch_since(self, since: datetime) -> list[RawEmail]:
        async with httpx.AsyncClient(timeout=30) as http:
            listing = await self._get(
                http,
                f"{GMAIL_API_BASE}/users/me/messages",
                params={"q": f"after:{int(since.timestamp())}", "maxResults": MAX_MESSAGES},
            )
            refs = listing.get("messages") or []
            emails: list[RawEmail] = []
            for ref in refs:
                message = await self._get(
                    http,
                    f"{GMAIL_API_BASE}/users/me/messages/{ref['id']}",
                    params={"format": "full"},
                )
                emails.append(_to_raw_email(message))
        log.info("gmail_fetched", count=len(emails))  # только счётчик (M4)
        return emails

    async def _get(
        self, http: httpx.AsyncClient, url: str, *, params: dict[str, Any]
    ) -> dict[str, Any]:
        if self._access_token is None:
            await self._refresh(http_hint=http)
        response = await http.get(url, params=params, headers=self._headers())
        if response.status_code == 401:
            # [S-C2]-паттерн: refresh и ровно один повтор
            await self._refresh(http_hint=http)
            response = await http.get(url, params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def _refresh(self, *, http_hint: httpx.AsyncClient) -> None:
        tokens = await refresh_access_token(
            client_id=self._client_id,
            client_secret=self._client_secret,
            refresh_token=self._refresh_token,
        )
        self._access_token = tokens.access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}


def _to_raw_email(message: dict[str, Any]) -> RawEmail:
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body_text = _extract_text(payload, "text/plain") or message.get("snippet", "")
    body_html = _extract_text(payload, "text/html")
    received_ms = int(message.get("internalDate", "0"))
    return RawEmail(
        gmail_id=message["id"],
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        snippet=message.get("snippet", ""),
        body_text=body_text,
        body_html=body_html,
        received_at=datetime.fromtimestamp(received_ms / 1000, tz=UTC),
        url=f"https://mail.google.com/mail/u/0/#inbox/{message['id']}",
    )


def _extract_text(payload: dict[str, Any], want_mime: str) -> str:
    """Вернуть декодированную часть нужного MIME (text/plain или text/html)."""
    candidates: list[tuple[str, str]] = []

    def walk(part: dict[str, Any]) -> None:
        data = part.get("body", {}).get("data")
        if data:
            candidates.append((part.get("mimeType", ""), data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    match = next((data for mime, data in candidates if mime == want_mime), None)
    if match is None:
        # для text/plain допускаем фолбэк на любую часть; для html — строго
        if want_mime == "text/plain" and candidates:
            match = candidates[0][1]
        else:
            return ""
    padded = match + "=" * (-len(match) % 4)
    return base64.urlsafe_b64decode(padded).decode(errors="replace")
