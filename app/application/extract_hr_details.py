"""Use case ExtractHrDetails (спека 006, US3 LLM-путь, [C-U5]/T6G).

LLM-путь «➕ собес»: из пересланного HR-сообщения LLM извлекает {date?, url?, gist}
(схема `HrDetails`, промпт `hr_extract_v1`) и дополняет interview_url/notes заявки
через СУЩЕСТВУЮЩИЙ AddInterviewDetails — статус НИКОГДА не меняется (C3).

Текст сообщения — недоверенные данные (R5, экранируется адаптером LlmPort). Тело
сообщения и извлечённая суть не логируются (M4) — только метаданные. Невалидный
вывод (R2) или пустое извлечение → мягкий фолбэк на ручной ввод (bot).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from opentelemetry import trace

from app.application.add_interview_details import AddInterviewDetails
from app.domain.correspondence import HrDetails
from app.domain.shared import PromptVersion
from app.ports.llm import LlmPort

log = structlog.get_logger("application.extract_hr_details")
tracer = trace.get_tracer("jobpilot.application")

ExtractStatus = Literal["extracted", "empty", "llm_failed", "not_found"]


@dataclass
class ExtractHrResult:
    status: ExtractStatus
    url: str | None = None
    notes: str | None = None


def _compose_notes(details: HrDetails) -> str | None:
    """Собирает заметку из даты и сути (уходит в Application.notes). Пусто → None."""
    parts: list[str] = []
    if details.date is not None:
        parts.append(f"Дата: {details.date.isoformat()}")
    gist = details.gist.strip()
    if gist:
        parts.append(gist)
    return " · ".join(parts) if parts else None


class ExtractHrDetails:
    def __init__(
        self,
        *,
        llm: LlmPort,
        details: AddInterviewDetails,
        system_prompt: str,
        prompt_version: PromptVersion,
    ) -> None:
        self._llm = llm
        self._details = details
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version

    async def run(self, vacancy_id: int, *, message_text: str) -> ExtractHrResult:
        with tracer.start_as_current_span("hr_extract.run") as span:
            span.set_attribute("vacancy.id", vacancy_id)
            verdict = await self._llm.complete(
                purpose="hr_extract",
                prompt_version=self._prompt_version,
                system=self._system_prompt,
                data=message_text,
                response_model=HrDetails,
            )
            if verdict is None:
                # адаптер уже сделал ровно один валидационный ретрай (R2) → фолбэк на ручной
                log.info("hr_extract_llm_failed", vacancy_id=vacancy_id)
                return ExtractHrResult(status="llm_failed")

            if verdict.is_empty:
                # нечего дополнять → мягкий фолбэк на ручной ввод (US3)
                log.info("hr_extract_empty", vacancy_id=vacancy_id)
                return ExtractHrResult(status="empty")

            url = verdict.url
            notes = _compose_notes(verdict)
            outcome = await self._details.run(vacancy_id, url=url, notes=notes)
            if outcome == "not_found":
                return ExtractHrResult(status="not_found")

            # M4: ни тело сообщения, ни суть не логируем — только факт и метаданные
            log.info(
                "hr_extract_applied",
                vacancy_id=vacancy_id,
                has_url=url is not None,
                has_date=verdict.date is not None,
            )
            return ExtractHrResult(status="extracted", url=url, notes=notes)
