"""Фейковый LlmPort для тестов и мок-режима: детерминизм + честный учёт llm_call (O1)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Sequence

import structlog
from pydantic import ValidationError

from app.domain.shared import PromptVersion
from app.obs.metrics import record_llm_metrics
from app.obs.tracing import current_trace_id
from app.ports.llm import LlmCallRecord, LlmCallRecorderPort, T, wrap_untrusted_data

log = structlog.get_logger("adapters.llm.fake")

MAX_RETRIES = 1  # инвариант R2: ровно один валидационный retry


class FakeLlm:
    """Программируемый провайдер: очередь сырых ответов, по одному на попытку."""

    def __init__(
        self,
        *,
        recorder: LlmCallRecorderPort,
        responses: Sequence[str] = (),
        model: str = "fake/model",
        include_cost_in_usage: bool = True,
        price_per_mtok_in: float = 0.10,
        price_per_mtok_out: float = 0.40,
        fake_cost_usd: float = 0.000123,
        fake_input_tokens: int = 120,
        fake_output_tokens: int = 25,
        response_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._recorder = recorder
        self._responses = list(responses)
        self._response_factory = response_factory
        self.model = model
        self._include_cost = include_cost_in_usage
        self._price_in = price_per_mtok_in
        self._price_out = price_per_mtok_out
        self._fake_cost = fake_cost_usd
        self._in_tokens = fake_input_tokens
        self._out_tokens = fake_output_tokens
        self.attempts = 0
        self.requested_models: list[str] = []
        self.sent_messages: list[dict[str, str]] = []

    async def complete(
        self,
        *,
        purpose: str,
        prompt_version: PromptVersion,
        system: str,
        data: str,
        response_model: type[T],
        few_shot: Sequence[tuple[str, str]] = (),
    ) -> T | None:
        started = time.perf_counter()
        self.sent_messages = _build_messages(system, data, few_shot)

        # мок-режим: очередь пуста → детерминированный ответ из фабрики
        if not self._responses and self._response_factory is not None:
            self._responses.append(self._response_factory(data))

        result: T | None = None
        attempts_left = 1 + MAX_RETRIES
        while attempts_left > 0 and self._responses:
            attempts_left -= 1
            self.attempts += 1
            self.requested_models.append(self.model)
            raw = self._responses.pop(0)
            try:
                result = response_model.model_validate_json(raw)
                break
            except ValidationError:
                log.warning("llm_invalid_output", purpose=purpose, model=self.model)
        else:
            if self.attempts == 0:
                # нет запрограммированных ответов — тоже graceful skip
                self.attempts += 1
                self.requested_models.append(self.model)
                log.warning("llm_no_response", purpose=purpose, model=self.model)

        if result is None:
            log.warning("llm_call_skipped", purpose=purpose, model=self.model)

        input_tokens = self._in_tokens * max(self.attempts, 1)
        output_tokens = self._out_tokens * max(self.attempts, 1)
        cost = (
            self._fake_cost
            if self._include_cost
            else input_tokens / 1_000_000 * self._price_in
            + output_tokens / 1_000_000 * self._price_out
        )
        await self._recorder.record(
            LlmCallRecord(
                purpose=purpose,
                model=self.model,
                prompt_version=prompt_version.as_str(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
                trace_id=current_trace_id(),
            )
        )
        record_llm_metrics(
            purpose=purpose,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        return result


_LOW_SCORE_MARKERS = ("продаж", "тестировщик", "junior", "1с")


def stub_scoring_response(data: str) -> str:
    """Детерминированный мок-скоринг для HH_MODE/LLM_MODE=fake.

    Скор — хеш текста в диапазоне 35..95; явный «мусор» (маркеры не-EM ролей)
    прижимается вниз, чтобы порог дайджеста (R4) было видно на моках.
    """
    digest = int(hashlib.sha256(data.encode()).hexdigest(), 16)
    lowered = data.lower()
    if any(marker in lowered for marker in _LOW_SCORE_MARKERS):
        score = 15 + digest % 30  # 15..44 — ниже порога 60
        reason = "Мок-скоринг: роль далека от Engineering Manager"
    else:
        score = 62 + digest % 34  # 62..95 — проходит порог
        reason = "Мок-скоринг: управленческая роль, похоже на профиль EM"
    return json.dumps({"score": score, "reason": reason}, ensure_ascii=False)


_JOB_MAIL_MARKERS = (
    "интервью",
    "собеседован",
    "ваканси",
    "оффер",
    "offer",
    "позици",
    "рекрутер",
    "resume",
    "резюме",
)


def stub_mail_response(data: str) -> str:
    """Детерминированный мок-классификатор писем (GMAIL_MODE/LLM_MODE=fake, этап 2)."""
    lowered = data.lower()
    if any(marker in lowered for marker in _JOB_MAIL_MARKERS):
        subject = next(
            (
                line[len("Subject: ") :]
                for line in data.splitlines()
                if line.startswith("Subject: ")
            ),
            "рабочее письмо",
        )
        summary = f"Мок-summary: {subject[:150]} — требуется ответ."
        return json.dumps({"is_job": True, "summary": summary}, ensure_ascii=False)
    return json.dumps({"is_job": False, "summary": "Не про работу."}, ensure_ascii=False)


def stub_invite_response(data: str) -> str:
    """Детерминированный мок инвайт-текста (этап 3, LLM_MODE=fake): ≤300, компания упомянута."""
    company = next(
        (
            line.split(":", 1)[1].strip()
            for line in data.splitlines()
            if line.startswith("Компания:")
        ),
        "вашей компанией",
    )
    text = (
        f"Здравствуйте! Я Engineering Manager (10+ лет: платформы, финтех). "
        f"Слежу за {company} — интересно, как устроена инженерная культура. "
        f"Буду рад связаться и обменяться опытом."
    )
    return json.dumps({"text": text[:300]}, ensure_ascii=False)


def _field_from_data(data: str, prefix: str, default: str) -> str:
    return next(
        (line.split(":", 1)[1].strip() for line in data.splitlines() if line.startswith(prefix)),
        default,
    )


def stub_letter_response(data: str) -> str:
    """Детерминированный мок сопроводительного письма (LLM_MODE=fake, этап 6E).

    Все факты — только из резюме EM (research §5); упоминает вакансию/компанию
    (рубрика eval), содержит 1–2 метрики из резюме, ≤2000 знаков, без канцелярита.
    """
    title = _field_from_data(data, "Вакансия:", "вашу вакансию")
    company = _field_from_data(data, "Компания:", "вашей компании")
    text = (
        f"Здравствуйте!\n\n"
        f"Меня заинтересовала роль «{title}» в {company}. "
        f"Я инженерный руководитель с 15+ годами в разработке и 10+ годами управления "
        f"командами.\n\n"
        f"Релевантный опыт из моего пути в Делимобиле:\n"
        f"- масштабировал мобильную команду x3 при текучести <10% и eNPS >90%;\n"
        f"- удержал crash-free на уровне 99% и снизил Tech Debt Index до 10%;\n"
        f"- внедрил Delivery Flow и CI/CD — 15+ продуктовых релизов в год.\n\n"
        f"Готов обсудить, чем этот опыт полезен вашей команде."
    )
    return json.dumps({"text": text[:2000]}, ensure_ascii=False)


_RU_MONTHS: dict[str, int] = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOTTED_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_RU_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн\w*|июл\w*|август\w*|"
    r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE,
)


def _extract_url(text: str) -> str | None:
    m = _URL_RE.search(text)
    if m is None:
        return None
    return m.group(0).rstrip(".,;)")


def _extract_date(text: str) -> str | None:
    """Детерминированный парс даты (ISO / ДД.ММ.ГГГГ / «20 августа [2026]»)→ ISO-строка.

    Русская дата без года требует явного года в тексте (детерминизм eval: без
    «текущего года»). Первое совпадение выигрывает.
    """
    iso = _ISO_RE.search(text)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    dotted = _DOTTED_RE.search(text)
    if dotted:
        day, month, year = (int(dotted.group(i)) for i in (1, 2, 3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    ru = _RU_DATE_RE.search(text)
    if ru and ru.group(3):
        ru_day = int(ru.group(1))
        month_word = ru.group(2).lower()
        ru_year = int(ru.group(3))
        ru_month = next(
            (num for stem, num in _RU_MONTHS.items() if month_word.startswith(stem)), None
        )
        if ru_month is not None:
            return f"{ru_year:04d}-{ru_month:02d}-{ru_day:02d}"
    return None


def stub_hr_response(data: str) -> str:
    """Детерминированный мок извлечения деталей собеса (LLM_MODE=fake, этап 6G).

    Парсит дату (ISO/ДД.ММ.ГГГГ/русский месяц с годом) и первую ссылку из текста
    HR-сообщения; суть (gist) — первая содержательная строка ≤200 знаков. Полностью
    детерминирован по тексту → eval hr_extract в fake воспроизводим (accuracy 1.0
    на согласованном датасете). Статус заявки не трогает (C3).
    """
    url = _extract_url(data)
    iso_date = _extract_date(data)
    first_line = next(
        (line.strip() for line in data.splitlines() if line.strip()),
        "",
    )
    gist = first_line[:200]
    return json.dumps({"date": iso_date, "url": url, "gist": gist}, ensure_ascii=False)


def _build_messages(
    system: str, data: str, few_shot: Sequence[tuple[str, str]]
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for user_example, assistant_example in few_shot:
        messages.append({"role": "user", "content": user_example})
        messages.append({"role": "assistant", "content": assistant_example})
    messages.append({"role": "user", "content": wrap_untrusted_data(data)})
    return messages
