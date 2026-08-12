"""[T406][T408] Контракт GetMatchSource: пагинация, вежливый доступ, изоляция (S4/S5).

- транспорт (httpx `/api/offers`) отделён от чистого `parse_getmatch_offers`;
- пагинация `offset += limit` до `meta.total`; дедуп по `id` между страницами (S1);
- пауза ≥ pause_sec между страницами (1 rps), честный User-Agent (guardrail);
- анти-бот (401/403/429/капча) → эскалация владельцу + GetMatchFetchError,
  обход НЕ строим (S5, constitution IV);
- 5xx/не-JSON первой страницы → GetMatchFetchError (коллектор изолирует → partial);
- сбой поздней страницы после собранного → отдаём собранное, без исключения (S4).

Сеть замокана httpx.MockTransport — CI без сети.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.getmatch.source import (
    GetMatchApiClient,
    GetMatchFetchError,
    GetMatchSource,
)
from app.domain.shared import Source

UA = "JobPilot/0.1 (personal-agent; owner-contact)"
API_URL = "https://getmatch.ru/api/offers"


def _offer(offer_id: int, position: str = "Engineering Manager") -> dict[str, object]:
    return {
        "id": offer_id,
        "position": position,
        "company": {"name": "Компания"},
        "url": f"/vacancies/{offer_id}-em",
        "salary_hidden": True,
        "offer_description": "<p>desc</p>",
        "is_active": True,
    }


def _page(offers: list[dict[str, object]], *, total: int, offset: int, limit: int) -> str:
    return json.dumps(
        {"meta": {"total": total, "offset": offset, "limit": limit}, "offers": offers}
    )


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class SleepSpy:
    def __init__(self, clock: Clock) -> None:
        self.calls: list[float] = []
        self._clock = clock

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self._clock.t += seconds


def make_client(handler: object, **kw: object) -> tuple[GetMatchApiClient, SleepSpy]:
    clock = Clock()
    sleep = SleepSpy(clock)
    client = GetMatchApiClient(
        api_url=API_URL,
        user_agent=UA,
        pause_sec=1.0,
        timeout_sec=5.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
        sleep=sleep,
        clock=clock,
        **kw,  # type: ignore[arg-type]
    )
    return client, sleep


class TestPagination:
    async def test_pages_until_total_and_dedups(self) -> None:
        seen_offsets: list[int] = []
        seen_ua: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("offset", "0"))
            limit = int(request.url.params.get("limit", "2"))
            seen_offsets.append(offset)
            seen_ua.append(request.headers.get("user-agent", ""))
            if offset == 0:
                return httpx.Response(
                    200, text=_page([_offer(1), _offer(2)], total=3, offset=0, limit=limit)
                )
            # вторая страница: один новый + повтор id=2 (дедуп между страницами)
            return httpx.Response(
                200, text=_page([_offer(2), _offer(3)], total=3, offset=offset, limit=limit)
            )

        client, sleep = make_client(handler)
        source = GetMatchSource(client=client, page_limit=2)
        vacancies = await source.fetch()

        assert source.name == "getmatch"
        assert {v.source_ref.external_id for v in vacancies} == {"1", "2", "3"}
        assert all(v.source_ref.source is Source.GETMATCH for v in vacancies)
        assert seen_offsets == [0, 2]  # offset += limit до total=3
        assert seen_ua[0] == UA  # честный UA
        assert any(s >= 1.0 for s in sleep.calls)  # пауза ≥1 c между страницами (1 rps)

    async def test_single_page_when_total_fits(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_page([_offer(1)], total=1, offset=0, limit=20))

        client, _ = make_client(handler)
        vacancies = await GetMatchSource(client=client, page_limit=20).fetch()
        assert [v.source_ref.external_id for v in vacancies] == ["1"]


class TestIsolation:
    async def test_anti_bot_escalates_and_raises(self) -> None:
        escalations: list[str] = []

        async def escalate(msg: str) -> None:
            escalations.append(msg)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        client, _ = make_client(handler)
        source = GetMatchSource(client=client, page_limit=20, escalate=escalate)
        with pytest.raises(GetMatchFetchError) as exc:
            await source.fetch()
        assert exc.value.kind == "anti_bot"
        assert len(escalations) == 1  # S5: обход НЕ строим — только эскалация
        assert "getmatch" in escalations[0].lower()

    async def test_captcha_marker_is_anti_bot(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>Please complete the CAPTCHA</html>")

        client, _ = make_client(handler)
        with pytest.raises(GetMatchFetchError) as exc:
            await GetMatchSource(client=client, page_limit=20).fetch()
        assert exc.value.kind == "anti_bot"

    async def test_5xx_first_page_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="down")

        client, _ = make_client(handler, max_retries=2)
        with pytest.raises(GetMatchFetchError) as exc:
            await GetMatchSource(client=client, page_limit=20).fetch()
        assert exc.value.kind == "http_error"

    async def test_non_json_first_page_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        client, _ = make_client(handler)
        with pytest.raises(GetMatchFetchError):
            await GetMatchSource(client=client, page_limit=20).fetch()

    async def test_later_page_failure_keeps_collected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(
                    200, text=_page([_offer(1), _offer(2)], total=4, offset=0, limit=2)
                )
            return httpx.Response(503, text="down")  # вторая страница падает

        client, _ = make_client(handler, max_retries=2)
        # уже собранное (стр.1) отдаётся, без исключения (S4, edge case spec)
        vacancies = await GetMatchSource(client=client, page_limit=2).fetch()
        assert {v.source_ref.external_id for v in vacancies} == {"1", "2"}


class TestApiClientRequest:
    async def test_sends_offset_limit_and_ua(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["offset"] = request.url.params.get("offset", "")
            captured["limit"] = request.url.params.get("limit", "")
            captured["ua"] = request.headers.get("user-agent", "")
            return httpx.Response(200, text=_page([_offer(1)], total=1, offset=0, limit=20))

        client, _ = make_client(handler)
        body = await client.fetch_page(offset=40, limit=20)
        assert captured == {"offset": "40", "limit": "20", "ua": UA}
        assert "offers" in body
