"""Мок Gmail-источника (GMAIL_MODE=fake): корпус писем всех веток префильтра.

Тот же InboxPort, что и будущий реальный адаптер (T210) — переключение конфигом.
Каждый fetch докидывает свежие письма рекрутёров (паттерн FakeHhVacancySource).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ports.inbox import RawEmail

_BASE_CORPUS: list[dict[str, str]] = [
    {
        "id": "mock-mail-1",
        "sender": "anna.recruiter@bigtech.io",
        "subject": "Позиция Engineering Manager — ответ на ваш отклик",
        "body": "Добрый день! Ваше резюме заинтересовало команду. Предлагаем интервью "
        "во вторник в 15:00. Подойдёт ли время?",
        "age_hours": "3",
    },
    {
        "id": "mock-mail-2",
        "sender": "hiring@fintechplus.ru",
        "subject": "Приглашение на техническое собеседование",
        "body": "Здравствуйте! Приглашаем вас на технический этап по позиции Head of Engineering.",
        "age_hours": "6",
    },
    {
        "id": "mock-mail-3",
        "sender": "digest@getmatch.ru",
        "subject": "Новые вакансии по вашему профилю",
        "body": "Подборка вакансий: EM в продуктовые команды, вилки от 350к.",
        "age_hours": "10",
    },
    {
        "id": "mock-mail-4",
        "sender": "promo@shop-megasale.ru",
        "subject": "Скидки до 70%! Успейте купить — unsubscribe",
        "body": "Только сегодня грандиозная распродажа!",
        "age_hours": "5",
    },
    {
        "id": "mock-mail-5",
        "sender": "invitations@linkedin.com",
        "subject": "Ivan Petrov wants to connect",
        "body": "Ivan Petrov, CTO at CloudCo, wants to connect with you on LinkedIn.",
        "age_hours": "8",
    },
    {
        "id": "mock-mail-6",
        "sender": "messages-noreply@linkedin.com",
        "subject": "You have a new message from Anna HR",
        "body": "Anna sent you a message about an Engineering Manager opportunity.",
        "age_hours": "12",
    },
    {
        "id": "mock-mail-7",
        "sender": "noreply@hh.ru",
        "subject": "Работодатель просмотрел ваш отклик",
        "body": "Компания «Ромашка» просмотрела ваш отклик на вакансию EM.",
        "age_hours": "4",
    },
    {
        "id": "mock-mail-8",
        "sender": "friend@gmail.com",
        "subject": "Шашлыки в субботу",
        "body": "Привет! Приезжай в субботу на дачу.",
        "age_hours": "14",
    },
]

_EXTRA_SENDERS = ("cto@dataworks.io", "talent@cloudnine.ru", "hr@telecom-neo.ru")


class FakeGmailInbox:
    """InboxPort: базовый корпус + новые письма рекрутёров на каждый fetch."""

    def __init__(self) -> None:
        self._fetches = 0

    async def fetch_since(self, since: datetime) -> list[RawEmail]:
        now = datetime.now(UTC)
        emails = [
            RawEmail(
                gmail_id=item["id"],
                sender=item["sender"],
                subject=item["subject"],
                snippet=item["body"][:100],
                body_text=item["body"],
                received_at=now - timedelta(hours=int(item["age_hours"])),
                url=f"https://mail.google.com/mail/u/0/#inbox/{item['id']}",
            )
            for item in _BASE_CORPUS
        ]
        for n in range(self._fetches):
            sender = _EXTRA_SENDERS[n % len(_EXTRA_SENDERS)]
            emails.append(
                RawEmail(
                    gmail_id=f"mock-extra-{n}",
                    sender=sender,
                    subject=f"Вакансия Engineering Manager #{n + 1}",
                    snippet="Рассмотрите нашу позицию EM.",
                    body_text="Здравствуйте! У нас открыта позиция EM, команда 8 человек.",
                    received_at=now - timedelta(minutes=30 + n),
                    url=f"https://mail.google.com/mail/u/0/#inbox/mock-extra-{n}",
                )
            )
        self._fetches += 1
        return [e for e in emails if e.received_at >= since]
