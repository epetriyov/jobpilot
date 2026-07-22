"""HhEmailSource — вакансии из писем HH «Вакансии по подписке» (пересмотр 2026-07-17).

Обход блокировок API/скрейпинга/userbot: HH сам шлёт подборки вакансий на почту,
а Gmail у нас подключён (этап 2). Парсер — чистая функция над HTML письма;
письма даёт InboxPort (реальный GmailInbox). Домен Sourcing не меняется.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import structlog
from bs4 import BeautifulSoup, Tag

from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy
from app.ports.inbox import InboxPort

log = structlog.get_logger("adapters.hh.email")

_VAC = re.compile(r"/vacancy/(\d+)")
_SALARY = re.compile(r"от\s+([\d\s ]+?)(?:\s+до\s+([\d\s ]+?))?\s*(?:₽|руб|р\.)", re.IGNORECASE)
_HH_SENDER = re.compile(r"hh\.ru", re.IGNORECASE)
# HH шлёт подборки под разными темами (формат менялся): «Вакансии по подписке»,
# «Новые вакансии …», «Подходящие вакансии для резюме …». Тело у всех одинаковое.
_VACANCY_SUBJECT = ("вакансии по подписке", "новые вакансии", "подходящие вакансии")
_REMOTE = ("можно удалённо", "можно удаленно")
# фрагменты зарплаты (реальные письма дробят «от 800 000 ₽» на отдельные строки)
_SALARY_TOKENS = ("от", "до", "₽", "руб", "руб.", "р.", "з/п", "на руки", "до вычета налогов")


def _is_salary_fragment(line: str) -> bool:
    low = line.lower().strip()
    if low in _SALARY_TOKENS:
        return True
    if re.fullmatch(r"[\d\s ]+", line):  # чистое число («800 000»)
        return True
    return bool(_SALARY.search(line))


def is_hh_vacancy_email(sender: str, subject: str) -> bool:
    """Письмо-подборка вакансий HH (а не отклик/просмотр резюме)."""
    if not _HH_SENDER.search(sender):
        return False
    lowered = subject.lower()
    return any(marker in lowered for marker in _VACANCY_SUBJECT)


def _salary(text: str) -> Salary:
    m = _SALARY.search(text)
    if not m:
        return Salary()
    to = int(re.sub(r"\D", "", m.group(2))) if m.group(2) else None
    return Salary(from_=int(re.sub(r"\D", "", m.group(1))), to=to, currency="RUR")


def _card_of(link: Tag) -> Tag:
    """Наименьший предок, следующий родитель которого содержит >1 вакансии."""
    node: Tag = link
    while node.parent is not None:
        parent = node.parent
        ids = {
            _VAC.search(str(a["href"])).group(1)  # type: ignore[union-attr]
            for a in parent.find_all("a", href=True)
            if _VAC.search(str(a["href"]))
        }
        if len(ids) > 1:
            return node
        node = parent
    return node


def parse_hh_email(html: str) -> list[Vacancy]:
    """HTML письма «Вакансии по подписке» → список Vacancy (дедуп по id)."""
    soup = BeautifulSoup(html, "html.parser")
    vacancies: list[Vacancy] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        m = _VAC.search(str(link["href"]))
        if m is None or not link.get_text(strip=True):
            continue
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)

        card = _card_of(link)
        lines = [s for s in card.stripped_strings if s.lower() != "посмотреть вакансию"]
        if len(lines) < 2:
            continue
        title = lines[0]
        # компания/локация — первая содержательная строка после названия: не фрагмент
        # зарплаты, не «удалёнка», с буквами (порядок строк в карточке HH непостоянен)
        company_line = next(
            (
                ln
                for ln in lines[1:]
                if not _is_salary_fragment(ln)
                and ln.lower() not in _REMOTE
                and re.search(r"[A-Za-zА-Яа-яЁё]", ln)
            ),
            "",
        )
        company = company_line.split(",", 1)[0].strip()
        location = company_line.split(",", 1)[1].strip() if "," in company_line else None
        vacancies.append(
            Vacancy.create(
                source_ref=SourceRef(source=Source.HH, external_id=vid),
                title=title,
                company=company,
                url=f"https://hh.ru/vacancy/{vid}",  # без utm/vss
                description_raw=" ".join(lines[2:]),
                salary=_salary(card.get_text(" ", strip=True)),
                location=location,
            )
        )
    return vacancies


class HhEmailSource:
    """VacancySourcePort поверх писем HH из Gmail (InboxPort)."""

    name = "hh"

    def __init__(self, *, inbox: InboxPort, since_hours: int = 48) -> None:
        self._inbox = inbox
        self._since_hours = since_hours

    async def fetch(self) -> list[Vacancy]:
        since = datetime.now(UTC) - timedelta(hours=self._since_hours)
        emails = await self._inbox.fetch_since(since)
        by_ref: dict[str, Vacancy] = {}
        letters = 0
        for mail in emails:
            if not is_hh_vacancy_email(mail.sender, mail.subject):
                continue
            letters += 1
            for vacancy in parse_hh_email(mail.body_html):
                by_ref.setdefault(vacancy.source_ref.as_key(), vacancy)
        log.info("hh_email_fetched", letters=letters, vacancies=len(by_ref))
        return list(by_ref.values())
