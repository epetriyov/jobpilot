"""Домен CORRESPONDENCE (DOMAIN.md §3.4): префильтр M1, схема summary M2, маршрутизация.

Кейсы: [M-U1] префильтр до LLM; [M-U2] summary ≤2 строк по схеме; [M-U3] LinkedIn-секция.
"""

import pytest
from pydantic import ValidationError

from app.domain.correspondence import MailVerdict, prefilter


class TestPrefilterMU1:
    """[M-U1] noreply@hh.ru — без LLM; рассылка магазина — отсечена до LLM (M1)."""

    def test_hh_notification_passes_without_llm(self) -> None:
        decision = prefilter(sender="noreply@hh.ru", subject="Новый отклик на вакансию")
        assert decision == "hidden"  # рабочее, но покрыто секцией negotiations этапа 1
        # ключевое: решение принято эвристикой, LLM не нужен
        assert decision != "llm"

    def test_shop_newsletter_dropped_before_llm(self) -> None:
        decision = prefilter(
            sender="promo@shop-megasale.ru",
            subject="Скидки до 70%! Успейте купить — unsubscribe в один клик",
        )
        assert decision == "drop"

    def test_whitelist_domain_goes_to_llm(self) -> None:
        assert prefilter(sender="hr@getmatch.ru", subject="Вакансия для вас") == "llm"

    def test_unknown_corporate_sender_goes_to_llm(self) -> None:
        """Неизвестный домен без промо-маркеров НЕ отсекается — рекрутёр с корп-почты
        важнее экономии токенов (ноль пропусков офферов, [M-E1])."""
        assert prefilter(sender="recruiter@bigtech.io", subject="Позиция EM") == "llm"


class TestLinkedInRoutingMU3:
    """[M-U3] Уведомление LinkedIn → source=linkedin_gmail, секция LinkedIn (без LLM)."""

    def test_wants_to_connect_routed_to_linkedin(self) -> None:
        decision = prefilter(
            sender="invitations@linkedin.com",
            subject="Ivan Petrov wants to connect",
        )
        assert decision == "linkedin"

    def test_linkedin_message_notification(self) -> None:
        decision = prefilter(
            sender="messages-noreply@linkedin.com",
            subject="You have a new message from Anna",
        )
        assert decision == "linkedin"


class TestMailVerdictMU2:
    """[M-U2] Summary длиннее лимита → реджект схемой (обрезку делает retry/фолбэк)."""

    def test_valid_verdict(self) -> None:
        verdict = MailVerdict(is_job=True, summary="Приглашение на интервью во вторник.")
        assert verdict.is_job

    def test_summary_over_limit_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MailVerdict(is_job=True, summary="х" * 201)

    def test_multiline_summary_over_two_lines_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MailVerdict(is_job=True, summary="строка 1\nстрока 2\nстрока 3")
