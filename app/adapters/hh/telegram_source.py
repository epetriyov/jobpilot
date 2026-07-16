"""HhTelegramSource — источник вакансий из HH-бота в Telegram (пересмотр 2026-07-15).

Парсер чистый (тестируется на golden-сообщениях); чтение диалога — через
TelegramMessageReaderPort (реальная реализация — Telethon userbot).
Непарсенное не роняет пайплайн: собирается в .unparsed для raw-секции ([S-C4]/S-C6).
"""

from __future__ import annotations

import re

import structlog

from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy
from app.ports.telegram_userbot import TelegramMessageReaderPort

log = structlog.get_logger("adapters.hh.telegram")

_VACANCY_URL = re.compile(r"https?://hh\.ru/vacancy/(\d+)")
# «от 350 000 до 450 000 ₽» / «от 500 000 ₽» — пробелы и NBSP внутри чисел
_SALARY = re.compile(
    r"от\s+([\d   ]+?)(?:\s+до\s+([\d   ]+?))?\s*(?:₽|руб|р\.)",
    re.IGNORECASE,
)
_HEADER_MARKERS = ("🔔", "новая вакансия", "по вашему резюме")


def _to_int(raw: str) -> int:
    return int(re.sub(r"[^\d]", "", raw))


def parse_hh_bot_message(text: str) -> Vacancy | None:
    """Одно сообщение HH-бота → Vacancy, либо None (нераспознанное → raw-секция)."""
    url_match = _VACANCY_URL.search(text)
    if url_match is None:
        return None  # не карточка вакансии (сводка/приветствие) → raw

    external_id = url_match.group(1)
    url = url_match.group(0)

    salary = Salary()
    salary_match = _SALARY.search(text)
    if salary_match:
        to = _to_int(salary_match.group(2)) if salary_match.group(2) else None
        salary = Salary(from_=_to_int(salary_match.group(1)), to=to, currency="RUR")

    # содержательные строки: без хедеров, зарплаты и url
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    content = [
        ln
        for ln in lines
        if not _VACANCY_URL.search(ln)
        and not _SALARY.search(ln)
        and not any(m in ln.lower() for m in _HEADER_MARKERS)
    ]
    if len(content) < 2:
        return None  # без title+company не собираем вакансию
    title, company = content[0], content[1]

    return Vacancy.create(
        source_ref=SourceRef(source=Source.HH, external_id=external_id),
        title=title,
        company=company,
        url=url,
        description_raw=text,
        salary=salary,
    )


class HhTelegramSource:
    """VacancySourcePort поверх сообщений HH-бота."""

    name = "hh"

    def __init__(self, *, reader: TelegramMessageReaderPort, bot_username: str) -> None:
        self._reader = reader
        self._bot_username = bot_username
        self.unparsed: list[str] = []

    async def fetch(self) -> list[Vacancy]:
        self.unparsed = []
        texts = await self._reader.recent_messages(self._bot_username)
        vacancies: list[Vacancy] = []
        for text in texts:
            vacancy = parse_hh_bot_message(text)
            if vacancy is None:
                self.unparsed.append(text)
                continue
            vacancies.append(vacancy)
        log.info("hh_telegram_fetched", parsed=len(vacancies), unparsed=len(self.unparsed))
        return vacancies


def render_raw_section(unparsed: list[str], limit: int = 5) -> str | None:
    """T117: непарсенные сообщения HH-бота — секцией «на проверку», не теряем (S-C6)."""
    if not unparsed:
        return None
    lines = [f"📨 HH-бот: {len(unparsed)} нераспознанных сообщений"]
    for text in unparsed[:limit]:
        first = text.strip().splitlines()[0] if text.strip() else "(пусто)"
        lines.append(f"• {first[:120]}")
    return "\n".join(lines)
