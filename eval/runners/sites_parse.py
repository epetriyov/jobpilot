"""Eval-контекст `sites_parse` ([S-C7], T540): field-completeness парсеров сайтов.

Для каждого зарегистрированного сайта: golden payload → parse_<site> → доля
заполненных полей. Пороги по data-model/spec: title/url/company = 100%,
location ≥ 90%. Salary опционален (в списках часто пуст — не штрафуем).

Чистый eval без LLM/сети: гоняется на записанных golden, годится для CI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from tests.golden.sites.harness import load_payload

from app.adapters.sites.avito import parse_avito
from app.adapters.sites.sber import parse_sber
from app.adapters.sites.tbank import parse_tbank
from app.adapters.sites.vk import parse_vk
from app.adapters.sites.yandex import parse_yandex
from app.domain.sourcing import Vacancy

ParseFn = Callable[[str], list[Vacancy]]

# site → (parser, имя golden-payload). Ozon (🔴) и Альфа (нет спайка) отсутствуют.
SITES: dict[str, tuple[ParseFn, str]] = {
    "yandex": (parse_yandex, "list.html"),
    "vk": (parse_vk, "list.html"),
    "avito": (parse_avito, "list.html"),
    "sber": (parse_sber, "publications.json"),
    "tbank": (parse_tbank, "vacancies.json"),
}

# Пороги полноты полей ([S-C7]).
THRESHOLDS: dict[str, float] = {"title": 1.0, "url": 1.0, "company": 1.0, "location": 0.9}


@dataclass
class SiteReport:
    site: str
    count: int
    completeness: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.count > 0 and all(
            self.completeness.get(f, 0.0) >= t for f, t in THRESHOLDS.items()
        )


def _completeness(vacancies: list[Vacancy]) -> dict[str, float]:
    n = len(vacancies)
    if n == 0:
        return dict.fromkeys(THRESHOLDS, 0.0)
    filled = {f: 0 for f in THRESHOLDS}
    for v in vacancies:
        if v.title:
            filled["title"] += 1
        if v.url:
            filled["url"] += 1
        if v.company:
            filled["company"] += 1
        if v.location:
            filled["location"] += 1
    return {f: c / n for f, c in filled.items()}


def evaluate_sites() -> list[SiteReport]:
    reports: list[SiteReport] = []
    for site, (parse_fn, payload_name) in SITES.items():
        vacancies = parse_fn(load_payload(site, payload_name))
        reports.append(
            SiteReport(site=site, count=len(vacancies), completeness=_completeness(vacancies))
        )
    return reports
