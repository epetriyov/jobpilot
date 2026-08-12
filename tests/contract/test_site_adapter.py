"""[T502][T503][S-C9][S-C10] Контракт SiteAdapter: транспорт↔парсер, изоляция падений.

- транспорт (fetch payload) отделён от чистого parse_fn (golden не зависит от добычи);
- падение транспорта (5xx/пусто/исключение) → SiteFetchError + scraper_failures{site} (S4);
- анти-бот/капча/логин-стена → SiteFetchError(kind="anti_bot") + эскалация владельцу;
  обход НЕ реализуется (S5, constitution IV);
- child-span на сайт (constitution V);
- EM-фильтр применяется после парсинга (FR-004).

Fake-транспорт: без реальной сети/браузера (CI-safe).
"""

from __future__ import annotations

import pytest

from app.adapters.sites.base import SiteAdapter, SiteFetchError
from app.adapters.sites.transport import (
    AntiBotError,
    EmptyResponseError,
    HttpStatusError,
)
from app.domain.shared import Source, SourceRef
from app.domain.sourcing import Vacancy

KEYWORDS = ["engineering manager", "тимлид"]


class FakeTransport:
    """Возвращает записанный payload либо бросает транспортную ошибку."""

    def __init__(self, *, payload: str = "", error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.calls = 0

    async def fetch(self) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._payload


def parse_two(payload: str) -> list[Vacancy]:
    """Чистый парсер-заглушка: payload игнорируется, отдаёт фикс. список."""
    titles = ["Engineering Manager", "Senior Developer"]
    return [
        Vacancy.create(
            source_ref=SourceRef(source=Source.SITE, site_name="yandex", external_id=t),
            title=t,
            company="Яндекс",
            url=f"https://yandex.ru/jobs/vacancies/{t}",
            description_raw="",
        )
        for t in titles
    ]


def make_adapter(transport: FakeTransport, **kw: object) -> SiteAdapter:
    return SiteAdapter(
        site_name="yandex",
        transport=transport,  # type: ignore[arg-type]
        parse_fn=parse_two,
        keywords=KEYWORDS,
        **kw,  # type: ignore[arg-type]
    )


class TestHappyPath:
    async def test_name_is_bare_site(self) -> None:
        adapter = make_adapter(FakeTransport(payload="<html/>"))
        assert adapter.name == "yandex"

    async def test_fetch_parses_then_em_filters(self) -> None:
        adapter = make_adapter(FakeTransport(payload="<html/>"))
        vacancies = await adapter.fetch()
        # parse дал 2, EM-фильтр оставил только руководящую роль (FR-004)
        assert [v.title for v in vacancies] == ["Engineering Manager"]
        assert all(v.source_ref.site_name == "yandex" for v in vacancies)

    async def test_self_reports_failures_flag(self) -> None:
        """Маркер для коллектора: метрику инкрементит адаптер, не дублировать."""
        adapter = make_adapter(FakeTransport(payload="<html/>"))
        assert adapter.self_reports_failures is True


class TestFailureIsolation:
    async def test_transport_5xx_raises_site_fetch_error(self) -> None:
        adapter = make_adapter(FakeTransport(error=HttpStatusError(503)))
        with pytest.raises(SiteFetchError) as exc:
            await adapter.fetch()
        assert exc.value.site == "yandex"
        assert exc.value.kind == "http_error"

    async def test_empty_response_raises(self) -> None:
        adapter = make_adapter(FakeTransport(error=EmptyResponseError()))
        with pytest.raises(SiteFetchError):
            await adapter.fetch()

    async def test_unexpected_exception_isolated(self) -> None:
        adapter = make_adapter(FakeTransport(error=RuntimeError("boom")))
        with pytest.raises(SiteFetchError) as exc:
            await adapter.fetch()
        assert exc.value.kind == "error"

    async def test_parser_break_is_isolated(self) -> None:
        def broken(_: str) -> list[Vacancy]:
            raise ValueError("HTML структура поплыла")

        adapter = SiteAdapter(
            site_name="yandex",
            transport=FakeTransport(payload="<html/>"),  # type: ignore[arg-type]
            parse_fn=broken,
            keywords=KEYWORDS,
        )
        with pytest.raises(SiteFetchError):
            await adapter.fetch()


class TestAntiBot:
    async def test_anti_bot_classified_and_escalated(self) -> None:
        escalations: list[str] = []

        async def escalate(msg: str) -> None:
            escalations.append(msg)

        adapter = make_adapter(FakeTransport(error=AntiBotError()), escalate=escalate)
        with pytest.raises(SiteFetchError) as exc:
            await adapter.fetch()
        assert exc.value.kind == "anti_bot"
        # S5: обход НЕ строим — только эскалация владельцу
        assert len(escalations) == 1
        assert "yandex" in escalations[0]

    async def test_anti_bot_without_escalate_still_raises(self) -> None:
        adapter = make_adapter(FakeTransport(error=AntiBotError()))
        with pytest.raises(SiteFetchError):
            await adapter.fetch()


class TestMetric:
    async def test_scraper_failures_incremented_with_site_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[int, dict[str, str]]] = []

        class SpyCounter:
            def add(self, amount: int, attrs: dict[str, str]) -> None:
                calls.append((amount, attrs))

        import app.adapters.sites.base as base_mod

        monkeypatch.setattr(base_mod, "scraper_failures_total", SpyCounter())
        adapter = make_adapter(FakeTransport(error=HttpStatusError(500)))
        with pytest.raises(SiteFetchError):
            await adapter.fetch()
        assert calls == [(1, {"site": "yandex"})]
