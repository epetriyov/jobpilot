"""SiteAdapter — общий каркас адаптера карьерного портала (VacancySourcePort).

Кросс-сайтовая механика в одном месте: изоляция падений → SiteFetchError +
scraper_failures{site} (S4, [S-C9]), классификация анти-бота (S5 — эскалация,
НЕ обход), child-span на сайт (constitution V), EM-фильтр после парсинга (FR-004).

Сайт-специфика — только в чистой функции parse_<site>(payload) -> list[Vacancy]
(без I/O) и в выбранном транспорте (httpx|Playwright). Домен НЕ меняется.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import NoReturn

import structlog
from opentelemetry import trace

from app.adapters.sites.em_filter import filter_em
from app.adapters.sites.transport import SiteTransport, TransportError
from app.domain.sourcing import SourceFetchFailed, Vacancy
from app.obs.metrics import scraper_failures_total

log = structlog.get_logger("adapters.sites")
tracer = trace.get_tracer("jobpilot.adapters.sites")

ParseFn = Callable[[str], list[Vacancy]]
EscalateFn = Callable[[str], Awaitable[None]]


class SiteFetchError(Exception):
    """Сбой сбора с сайта. Коллектор изолирует (S4): партиал, остальные собраны."""

    def __init__(self, site: str, kind: str) -> None:
        super().__init__(f"site:{site} fetch failed ({kind})")
        self.site = site
        self.kind = kind


class SiteAdapter:
    """VacancySourcePort поверх (транспорт → parse_<site> → EM-фильтр)."""

    # Маркер для коллектора (RunDailyDigest): метрику scraper_failures адаптер
    # инкрементит сам — коллектор её НЕ дублирует, но считает источник упавшим.
    self_reports_failures = True

    def __init__(
        self,
        *,
        site_name: str,
        transport: SiteTransport,
        parse_fn: ParseFn,
        keywords: Sequence[str],
        escalate: EscalateFn | None = None,
    ) -> None:
        # name — метка метрики scraper_failures{site} и source в логах: «голое»
        # имя сайта. Обычный атрибут (не property) — так требует VacancySourcePort.
        self.name = site_name
        self._site_name = site_name
        self._transport = transport
        self._parse_fn = parse_fn
        self._keywords = list(keywords)
        self._escalate = escalate

    async def fetch(self) -> list[Vacancy]:
        with tracer.start_as_current_span("site.fetch") as span:
            span.set_attribute("site.name", self._site_name)
            try:
                payload = await self._transport.fetch()
                vacancies = self._parse_fn(payload)
            except TransportError as exc:
                await self._fail(exc.kind, exc)
            except Exception as exc:  # неожиданное (в т.ч. слом парсера) — тоже изолируем
                await self._fail("error", exc)
            kept = filter_em(vacancies, self._keywords)
            span.set_attribute("vacancies.in", len(vacancies))
            span.set_attribute("vacancies.kept", len(kept))
            return kept

    async def _fail(self, kind: str, cause: Exception) -> NoReturn:
        scraper_failures_total.add(1, {"site": self._site_name})
        event = SourceFetchFailed(source=f"site:{self._site_name}", error=kind)
        span = trace.get_current_span()
        span.set_attribute("error", True)
        span.set_attribute("site.error_kind", kind)
        if kind == "anti_bot":
            # S5 (constitution IV): обход НЕ строим — эскалируем владельцу.
            log.warning("site_anti_bot", source=event.source, error=event.error)
            if self._escalate is not None:
                await self._escalate(
                    f"⛔ Портал site:{self._site_name} включил анти-бот/капчу. "
                    "Обход не выполняется (S5) — сбор с сайта остановлен."
                )
        else:
            log.warning(
                "source_fetch_failed", source=event.source, error=event.error, cause=str(cause)
            )
        raise SiteFetchError(self._site_name, kind) from cause
