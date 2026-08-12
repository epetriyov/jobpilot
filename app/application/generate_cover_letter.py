"""Use case GenerateCoverLetter (спека 006, US 6E, [M-C3]): письмо под вакансию.

Факты — только из резюме EM (система-промпт собирается в composition из resumes/);
текст вакансии — недоверенные данные (R5, экранируется адаптером). Модель — Pro
(`LLM_MODEL_LETTERS`, выбирается в composition). Невалидный вывод → 1 retry в
адаптере (R2) → graceful. Persist в cover_letter (🔁 — новая версия). Отправку
письма делает человек вручную (M3/VI). Тело письма не логируется (M4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from opentelemetry import trace

from app.domain.correspondence import CoverLetter, CoverLetterOut
from app.domain.shared import PromptVersion
from app.ports.llm import LlmPort
from app.ports.notifier import CoverLetterCard, NotifierPort
from app.ports.repositories import CoverLetterRepositoryPort, VacancyReaderPort

log = structlog.get_logger("application.generate_cover_letter")
tracer = trace.get_tracer("jobpilot.application")

GenerateStatus = Literal["generated", "vacancy_not_found", "llm_failed"]


@dataclass
class GenerateCoverLetterResult:
    status: GenerateStatus
    letter_id: int | None = None


class GenerateCoverLetter:
    def __init__(
        self,
        *,
        llm: LlmPort,
        vacancy_reader: VacancyReaderPort,
        letter_repo: CoverLetterRepositoryPort,
        notifier: NotifierPort,
        system_prompt: str,
        prompt_version: PromptVersion,
    ) -> None:
        self._llm = llm
        self._reader = vacancy_reader
        self._repo = letter_repo
        self._notifier = notifier
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version

    async def run(self, vacancy_id: int) -> GenerateCoverLetterResult:
        with tracer.start_as_current_span("cover_letter.generate") as span:
            span.set_attribute("vacancy.id", vacancy_id)
            snapshot = await self._reader.get_by_id(vacancy_id)
            if snapshot is None:
                await self._notifier.send_message(
                    f"✉️ Не нашёл вакансию #{vacancy_id} в хранилище 🤔"
                )
                return GenerateCoverLetterResult(status="vacancy_not_found")

            data = (
                f"Вакансия: {snapshot.title}\n"
                f"Компания: {snapshot.company}\n\n"
                f"{snapshot.description_text}"
            )
            verdict = await self._llm.complete(
                purpose="cover",
                prompt_version=self._prompt_version,
                system=self._system_prompt,
                data=data,
                response_model=CoverLetterOut,
            )
            if verdict is None:
                # адаптер уже сделал ровно один валидационный ретрай (R2)
                await self._notifier.send_message(
                    "✉️ Не получилось сгенерировать письмо — попробуйте ещё раз позже."
                )
                log.warning("cover_letter_llm_failed", vacancy_id=vacancy_id)
                return GenerateCoverLetterResult(status="llm_failed")

            letter = CoverLetter(
                vacancy_id=vacancy_id,
                text=verdict.text,
                prompt_version=self._prompt_version.as_str(),
            )
            letter_id = await self._repo.add(letter)
            await self._notifier.send_cover_letter_card(
                CoverLetterCard(
                    vacancy_id=vacancy_id,
                    title=snapshot.title,
                    company=snapshot.company,
                    text=verdict.text,
                )
            )
            # M4: тело письма не логируется — только метаданные
            log.info(
                "cover_letter_generated",
                vacancy_id=vacancy_id,
                letter_id=letter_id,
                length=len(verdict.text),
            )
            return GenerateCoverLetterResult(status="generated", letter_id=letter_id)
