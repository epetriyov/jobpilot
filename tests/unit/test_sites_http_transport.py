"""[T502][S-C10] HttpTransport: вежливый httpx-транспорт для лёгких сайтов.

- ≥ rate_limit_sec между запросами к одному порталу;
- честный User-Agent из конфига в заголовке;
- таймаут/ретраи (5xx → ретрай → HttpStatusError);
- проверка robots.txt целевого пути (Disallow → RobotsDisallowedError, портал не читается);
- анти-бот (403/429/капча-маркер) → AntiBotError (S5, обход не строим);
- пустой ответ → EmptyResponseError.

Сеть замокана httpx.MockTransport — CI без сети.
"""

from __future__ import annotations

import httpx
import pytest

from app.adapters.sites.http_transport import HttpTransport
from app.adapters.sites.transport import (
    AntiBotError,
    EmptyResponseError,
    HttpStatusError,
    RobotsDisallowedError,
)

UA = "JobPilot/1.0 (+owner-contact)"


def make_client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def robots(body: str = "User-agent: *\nAllow: /") -> httpx.Response:
    return httpx.Response(200, text=body)


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
        self._clock.t += seconds  # эмулируем ход времени


def build(
    handler: object, *, robots_respect: bool = True, **kw: object
) -> tuple[HttpTransport, SleepSpy]:
    clock = Clock()
    sleep = SleepSpy(clock)
    transport = HttpTransport(
        url="https://yandex.ru/jobs/vacancies",
        user_agent=UA,
        rate_limit_sec=1.0,
        timeout_sec=5.0,
        robots_respect=robots_respect,
        client=make_client(handler),
        sleep=sleep,
        clock=clock,
        **kw,  # type: ignore[arg-type]
    )
    return transport, sleep


class TestHappyPath:
    async def test_returns_body_and_sends_user_agent(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            seen["ua"] = request.headers.get("user-agent", "")
            return httpx.Response(200, text="<html>vac</html>")

        transport, _ = build(handler)
        body = await transport.fetch()
        assert body == "<html>vac</html>"
        assert seen["ua"] == UA


class TestRateLimit:
    async def test_pause_between_sequential_requests(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            return httpx.Response(200, text="ok")

        transport, sleep = build(handler)
        await transport.fetch()
        await transport.fetch()
        # второй запрос обязан подождать ≥1 s (первый — без ожидания)
        assert any(s >= 1.0 for s in sleep.calls)


class TestRobots:
    async def test_disallow_blocks_fetch(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots("User-agent: *\nDisallow: /jobs")
            return httpx.Response(200, text="should-not-reach")

        transport, _ = build(handler)
        with pytest.raises(RobotsDisallowedError):
            await transport.fetch()

    async def test_respect_off_skips_robots(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path != "/robots.txt"  # robots не запрашивается
            return httpx.Response(200, text="ok")

        transport, _ = build(handler, robots_respect=False)
        assert await transport.fetch() == "ok"

    async def test_query_root_disallow_does_not_block_path(self) -> None:
        """Регресс: `Disallow: /?` (квирк Яндекса — блок только query-root `/?...`)
        НЕ должен блокировать обычный путь `/jobs/vacancies`. stdlib RobotFileParser
        нормализует правило в `Disallow: /` и роняет весь сайт — protego парсит верно."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots(
                    "User-agent: *\nDisallow: /?\nDisallow: /jobs/skill-diagnostic/private/*\n"
                )
            return httpx.Response(200, text="<html>vac</html>")

        transport, _ = build(handler)
        assert await transport.fetch() == "<html>vac</html>"

    async def test_real_prohibition_still_blocks(self) -> None:
        """Реальный запрет обязан продолжать блокировать: `Disallow: /api/` на
        целевом пути `/api/offers` → RobotsDisallowedError (не ослабляем guardrail)."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots("User-agent: *\nDisallow: /api/\n")
            return httpx.Response(200, text="should-not-reach")

        clock = Clock()
        sleep = SleepSpy(clock)
        transport = HttpTransport(
            url="https://getmatch.ru/api/offers",
            user_agent=UA,
            rate_limit_sec=1.0,
            timeout_sec=5.0,
            client=make_client(handler),
            sleep=sleep,
            clock=clock,
        )
        with pytest.raises(RobotsDisallowedError):
            await transport.fetch()


class TestFailures:
    async def test_5xx_retries_then_http_error(self) -> None:
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            attempts["n"] += 1
            return httpx.Response(503, text="down")

        transport, _ = build(handler, max_retries=2)
        with pytest.raises(HttpStatusError):
            await transport.fetch()
        assert attempts["n"] >= 2  # был ретрай

    async def test_403_is_anti_bot(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            return httpx.Response(403, text="forbidden")

        transport, _ = build(handler)
        with pytest.raises(AntiBotError):
            await transport.fetch()

    async def test_captcha_marker_is_anti_bot(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            return httpx.Response(200, text="<html>Please complete the CAPTCHA</html>")

        transport, _ = build(handler)
        with pytest.raises(AntiBotError):
            await transport.fetch()

    async def test_smartcaptcha_wall_is_anti_bot(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            return httpx.Response(200, text="<html><body>SmartCaptcha checkpoint</body></html>")

        transport, _ = build(handler)
        with pytest.raises(AntiBotError):
            await transport.fetch()

    async def test_captcha_sdk_reference_is_not_anti_bot(self) -> None:
        """Регресс: легитимная страница со ссылкой на captcha-SDK (виджет логина) —
        НЕ анти-бот. VK Team отдаёт вакансии на 200 с `initialVacancies`, но в теле
        висит `static.vk.ru/captchaSDK/loader` для формы входа — голый маркер
        `captcha` ложно ронял рабочий источник в AntiBotError."""
        vk_body = (
            "<html><head><title>Вакансии</title></head><body>"
            '<script src="https://static.vk.ru/captchaSDK/loader/1/umd/index.js" defer></script>'
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"initialVacancies":[{"id":52461,"title":"Секретарь"}]}}}'
            "</script></body></html>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            return httpx.Response(200, text=vk_body)

        transport, _ = build(handler)
        assert await transport.fetch() == vk_body

    async def test_empty_body_is_empty_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            return httpx.Response(200, text="   ")

        transport, _ = build(handler)
        with pytest.raises(EmptyResponseError):
            await transport.fetch()


class TestPost:
    async def test_post_sends_json_body(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return robots()
            captured["method"] = request.method
            captured["content"] = request.content
            return httpx.Response(200, text='{"payload":{}}')

        clock = Clock()
        sleep = SleepSpy(clock)
        transport = HttpTransport(
            url="https://www.tbank.ru/pfpjobs/papi/getVacancies",
            method="POST",
            json_body={"offset": 0},
            user_agent=UA,
            rate_limit_sec=1.0,
            timeout_sec=5.0,
            client=make_client(handler),
            sleep=sleep,
            clock=clock,
        )
        await transport.fetch()
        assert captured["method"] == "POST"
        assert b"offset" in captured["content"]  # type: ignore[operator]
