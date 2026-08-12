"""Eval-контекст `hr_extract` ([C-E1], T6G-3): извлечение даты/ссылки из HR-сообщений.

Для каждого обезличенного сообщения HR:
  1) извлекаем детали (purpose="hr_extract", промпт hr_extract_v1, схема HrDetails) —
     как в ExtractHrDetails;
  2) сравниваем извлечённые `date` и `url` с эталоном датасета.

Порог ([C-E1]): **accuracy по дате И по ссылке ≥0.9**. Дата сравнивается как ISO-строка
(и «нет даты» = null против null — тоже совпадение), ссылка — как строка. Провайдер:
real (OpenRouter) при ключе и без EVAL_FAKE; иначе детерминированный стаб (парсит
дату/ссылку из текста → воспроизводимо, accuracy 1.0 на согласованном датасете).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.llm.fake import FakeLlm, stub_hr_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.config import Settings
from app.domain.correspondence import HrDetails
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord, LlmPort

HR_PV = PromptVersion(purpose="hr_extract", version=1)


class _Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


@dataclass
class HrMetrics:
    model: str
    total: int
    date_correct: int
    url_correct: int
    llm_errors: int  # LLM не отдал валидную схему за все попытки — инфра, вне знаменателя

    @property
    def evaluable(self) -> int:
        return self.total - self.llm_errors

    @property
    def date_accuracy(self) -> float:
        return self.date_correct / self.evaluable if self.evaluable else 0.0

    @property
    def url_accuracy(self) -> float:
        return self.url_correct / self.evaluable if self.evaluable else 0.0

    @property
    def ok(self) -> bool:
        return self.date_accuracy >= 0.9 and self.url_accuracy >= 0.9


def _llm(recorder: _Recorder, *, use_real: bool, settings: Settings) -> tuple[LlmPort, str]:
    if use_real:
        llm = InstructorOpenRouterLlm(settings=settings, recorder=recorder)
        return llm, settings.llm_model_summary
    return FakeLlm(recorder=recorder, model="fake/hr", response_factory=stub_hr_response), "fake/hr"


def _norm_date(value: str | None) -> str | None:
    return value or None


def _norm_url(value: str | None) -> str | None:
    return value.rstrip("/") if value else None


async def extract_dataset(
    examples: list[dict],  # type: ignore[type-arg]
    *,
    recorder: _Recorder,
    use_real: bool,
    settings: Settings,
) -> HrMetrics:
    llm, model = _llm(recorder, use_real=use_real, settings=settings)
    system = load_system_prompt("hr_extract", HR_PV.version)
    date_correct = url_correct = llm_errors = 0

    for ex in examples:
        message = ex["input"]["message"]
        expected = ex["expected"]
        exp_date = _norm_date(expected.get("date"))
        exp_url = _norm_url(expected.get("url"))

        verdict: HrDetails | None = await llm.complete(
            purpose="hr_extract",
            prompt_version=HR_PV,
            system=system,
            data=message,
            response_model=HrDetails,
        )
        if verdict is None:
            llm_errors += 1
            continue

        got_date = verdict.date.isoformat() if verdict.date is not None else None
        got_url = _norm_url(verdict.url)
        if got_date == exp_date:
            date_correct += 1
        if got_url == exp_url:
            url_correct += 1

    return HrMetrics(
        model=model,
        total=len(examples),
        date_correct=date_correct,
        url_correct=url_correct,
        llm_errors=llm_errors,
    )
