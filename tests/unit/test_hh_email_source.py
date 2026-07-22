"""HH email-источник (пересмотр 2026-07-17): вакансии из писем «Вакансии по подписке».

Парсер — чистая функция над HTML письма (golden по реальной структуре);
письма даёт InboxPort (реальный — GmailInbox этапа 2).
"""

from datetime import UTC, datetime
from pathlib import Path

from app.adapters.hh.email_source import (
    HhEmailSource,
    is_hh_vacancy_email,
    parse_hh_email,
)
from app.ports.inbox import RawEmail

GOLDEN = Path(__file__).parent.parent / "golden" / "hh_email"


def golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


class TestParse:
    def test_extracts_all_vacancies(self) -> None:
        vacancies = parse_hh_email(golden("subscription.html"))
        assert [v.source_ref.as_key() for v in vacancies] == [
            "hh:200000001",
            "hh:200000002",
            "hh:200000003",
            "hh:200000004",
        ]

    def test_salary_before_company_line(self) -> None:
        """Порядок строк непостоянен: зарплата может идти перед компанией."""
        v4 = next(
            v
            for v in parse_hh_email(golden("subscription.html"))
            if v.source_ref.external_id == "200000004"
        )
        assert v4.company == "МедТех Сервис"  # не «от»
        assert v4.salary.from_ == 800_000

    def test_fields_company_from_first_segment(self) -> None:
        first, second, third, _ = parse_hh_email(golden("subscription.html"))
        assert first.title == "Engineering Manager"
        assert first.company == "Ромашка Технологии"  # до первой запятой
        assert first.location == "Москва, м. Спортивная, Фрунзенская"
        assert (first.salary.from_, first.salary.to) == (350_000, 450_000)
        # «от X» без «до»
        assert (second.salary.from_, second.salary.to) == (500_000, None)
        assert second.company == "Финтех Плюс"
        # без зарплаты
        assert third.salary.from_ is None

    def test_url_cleaned_of_tracking(self) -> None:
        first = parse_hh_email(golden("subscription.html"))[0]
        assert first.url == "https://hh.ru/vacancy/200000001"  # utm/vss отрезаны

    def test_dedup_title_and_cta_links(self) -> None:
        # каждая вакансия — 2 ссылки (заголовок + «Посмотреть»), но карточка одна
        assert len(parse_hh_email(golden("subscription.html"))) == 4


class TestIsVacancyEmail:
    def test_subscription_subject(self) -> None:
        assert is_hh_vacancy_email("noreply@hh.ru", "Вакансии по подписке: Все вакансии")
        assert is_hh_vacancy_email('"hh.ru" <noreply@hh.ru>', "Новые вакансии по запросу")
        # формат HH менялся (2026-07): «Подходящие вакансии для резюме …» — тоже подборка
        assert is_hh_vacancy_email(
            '"hh.ru" <noreply@hh.ru>', "Подходящие вакансии для резюме: «Head Of Development»"
        )

    def test_non_vacancy_hh_email(self) -> None:
        assert not is_hh_vacancy_email("noreply@hh.ru", "Вчера ваше резюме привлекло внимание")
        assert not is_hh_vacancy_email("noreply@hh.ru", "Работодатель не готов пригласить вас")

    def test_non_hh_sender(self) -> None:
        assert not is_hh_vacancy_email("promo@shop.ru", "Вакансии по подписке")


class InboxFake:
    def __init__(self, emails: list[RawEmail]) -> None:
        self._emails = emails

    async def fetch_since(self, since: datetime) -> list[RawEmail]:
        return self._emails


def email(gmail_id: str, sender: str, subject: str, html: str = "") -> RawEmail:
    return RawEmail(
        gmail_id=gmail_id,
        sender=sender,
        subject=subject,
        snippet="",
        body_text="",
        body_html=html,
        received_at=datetime(2026, 7, 17, tzinfo=UTC),
        url=f"https://mail.google.com/#inbox/{gmail_id}",
    )


class TestSource:
    async def test_fetch_parses_only_vacancy_emails(self) -> None:
        emails = [
            email("e1", "noreply@hh.ru", "Вакансии по подписке", golden("subscription.html")),
            email("e2", "noreply@hh.ru", "Вчера ваше резюме привлекло внимание", "<html></html>"),
            email("e3", "promo@shop.ru", "Скидки", "<html></html>"),
        ]
        source = HhEmailSource(inbox=InboxFake(emails), since_hours=48)

        vacancies = await source.fetch()

        assert source.name == "hh"
        assert len(vacancies) == 4  # только из письма-подписки
        assert all(v.source_ref.source == "hh" for v in vacancies)

    async def test_dedup_across_emails(self) -> None:
        # одна вакансия в двух письмах → один Vacancy (дедуп по source_ref в источнике)
        emails = [
            email("e1", "noreply@hh.ru", "Вакансии по подписке", golden("subscription.html")),
            email("e2", "noreply@hh.ru", "Вакансии по подписке", golden("subscription.html")),
        ]
        source = HhEmailSource(inbox=InboxFake(emails), since_hours=48)
        assert len(await source.fetch()) == 4
