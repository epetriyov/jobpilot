"""Eval-контекст `cover_letter` ([M-E2], T6E-5): анти-галлюцинации + рубрика.

Для каждой вакансии:
  1) генерируем письмо (purpose="cover", промпт cover_v1 + резюме EM + гайд) — как в
     GenerateCoverLetter; модель — `LLM_MODEL_LETTERS` (Pro);
  2) детерминированные проверки: длина ≤2000 (M3) и обращение к вакансии
     (title/company упомянуты);
  3) LLM-судья (purpose="judge", `LLM_MODEL_JUDGE`) fact-check'ит КАЖДЫЙ фактологический
     тезис письма против резюме → список неподтверждённых фактов (`hallucinations`),
     плюс рубрика (метрика из резюме, без канцелярита).

Порог ([M-E2]): **hallucinations = 0 — блокер** (любой неподтверждённый факт = FAIL) И
рубрика pass-rate ≥0.9 среди оценённых. Инфра-сбои судьи — вне знаменателя (как
invite_rubric). Провайдер: real (OpenRouter) при ключе и без EVAL_FAKE; иначе стаб
(судья в fake всегда «hallucinations=[]» — fake проверяет валидность схемы, не факты).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from app.adapters.llm.fake import FakeLlm, stub_letter_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.config import Settings
from app.domain.correspondence import COVER_LETTER_MAX_CHARS, CoverLetterOut
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord, LlmPort

COVER_PV = PromptVersion(purpose="cover", version=1)
JUDGE_PV = PromptVersion(purpose="judge", version=1)
JUDGE_ATTEMPTS = 3  # добор при обрыве JSON судьи (инфра-флап, не рубрика)

_ROOT = Path(__file__).resolve().parents[2]
_RESUME_PATH = _ROOT / "resumes" / "resume_em.md"
_GUIDE_PATH = _ROOT / "resumes" / "cover_letter_guide.md"

# Рубрика судьи (eval-локальная, не продовый промпт). Резюме + письмо — в блоке данных.
JUDGE_SYSTEM = (
    "Ты — придирчивый fact-checker сопроводительных писем. В блоке данных: РЕЗЮМЕ "
    "кандидата (единственный источник истины), текст вакансии и ТЕКСТ ПИСЬМА.\n"
    "Задача: для КАЖДОГО фактологического утверждения письма (компания, должность, "
    "срок, метрика, цифра, технология, достижение) проверь, подтверждается ли оно "
    "резюме. Любой факт, которого НЕТ в резюме или который ему противоречит, — "
    "галлюцинация. Общие вежливые фразы и пересказ требований вакансии галлюцинациями "
    "не считаются.\n"
    "Верни строгий JSON:\n"
    '{"hallucinations": [<кратко каждый неподтверждённый факт>], '
    '"has_metric": <bool: есть ≥1 релевантная метрика из резюме>, '
    '"no_cliche": <bool: без канцелярита и штампов>, '
    '"reason": <строка ≤200>}'
)


class CoverJudge(BaseModel):
    hallucinations: list[str] = Field(default_factory=list)
    has_metric: bool
    no_cliche: bool
    reason: str = Field(max_length=200)


def _stub_cover_judge_response(_data: str) -> str:
    return json.dumps(
        {"hallucinations": [], "has_metric": True, "no_cliche": True, "reason": "fake: ok"},
        ensure_ascii=False,
    )


class _Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


@dataclass
class CoverMetrics:
    gen_model: str
    judge_model: str
    total: int
    passed: int
    fail_length: int
    fail_addresses: int
    fail_rubric: int
    hallucination_count: int  # суммарно неподтверждённых фактов (блокер: должно быть 0)
    examples_with_hallucinations: int
    judge_errors: int  # судья не отдал схему за все попытки — инфра, вне знаменателя

    @property
    def evaluable(self) -> int:
        return self.total - self.judge_errors

    @property
    def rubric_pass_rate(self) -> float:
        return self.passed / self.evaluable if self.evaluable else 0.0

    @property
    def ok(self) -> bool:
        # блокер: 0 галлюцинаций; плюс рубрика ≥0.9 среди оценённых
        return self.hallucination_count == 0 and self.rubric_pass_rate >= 0.9


def _cover_system_prompt() -> str:
    parts = [load_system_prompt("cover", COVER_PV.version)]
    if _RESUME_PATH.exists():
        parts.append(
            "## Резюме (единственный источник фактов)\n" + _RESUME_PATH.read_text(encoding="utf-8")
        )
    if _GUIDE_PATH.exists():
        parts.append(
            "## Гайд по письмам (рекомендации, не источник фактов)\n"
            + _GUIDE_PATH.read_text(encoding="utf-8")
        )
    return "\n\n".join(parts)


def _resume_text() -> str:
    return _RESUME_PATH.read_text(encoding="utf-8") if _RESUME_PATH.exists() else ""


def _llms(
    recorder: _Recorder, *, use_real: bool, settings: Settings
) -> tuple[LlmPort, LlmPort, str, str]:
    if use_real:
        llm = InstructorOpenRouterLlm(settings=settings, recorder=recorder)
        return llm, llm, settings.llm_model_letters, settings.llm_model_judge
    gen = FakeLlm(recorder=recorder, model="fake/cover", response_factory=stub_letter_response)
    judge = FakeLlm(
        recorder=recorder, model="fake/judge", response_factory=_stub_cover_judge_response
    )
    return gen, judge, "fake/cover", "fake/judge"


async def judge_dataset(
    examples: list[dict],  # type: ignore[type-arg]
    *,
    recorder: _Recorder,
    use_real: bool,
    settings: Settings,
) -> CoverMetrics:
    gen_llm, judge_llm, gen_model, judge_model = _llms(
        recorder, use_real=use_real, settings=settings
    )
    system = _cover_system_prompt()
    resume = _resume_text()
    passed = fail_length = fail_addresses = fail_rubric = 0
    hallucination_count = examples_with_hallucinations = judge_errors = 0

    for ex in examples:
        title = ex["input"]["title"]
        company = ex["input"]["company"]
        vacancy_text = ex["input"]["vacancy_text"]
        data = f"Вакансия: {title}\nКомпания: {company}\n\n{vacancy_text}"

        letter = await gen_llm.complete(
            purpose="cover",
            prompt_version=COVER_PV,
            system=system,
            data=data,
            response_model=CoverLetterOut,
        )
        if letter is None or len(letter.text) > COVER_LETTER_MAX_CHARS:
            fail_length += 1
            continue
        lowered = letter.text.lower()
        if title.lower() not in lowered and company.lower() not in lowered:
            fail_addresses += 1
            continue

        judge_data = (
            f"РЕЗЮМЕ:\n{resume}\n\n"
            f"ВАКАНСИЯ: {title} — {company}\n{vacancy_text}\n\n"
            f"ТЕКСТ ПИСЬМА:\n{letter.text}"
        )
        verdict: CoverJudge | None = None
        for _ in range(JUDGE_ATTEMPTS):
            verdict = await judge_llm.complete(
                purpose="judge",
                prompt_version=JUDGE_PV,
                system=JUDGE_SYSTEM,
                data=judge_data,
                response_model=CoverJudge,
            )
            if verdict is not None:
                break
        if verdict is None:
            judge_errors += 1
            continue

        n_hallucinations = len(verdict.hallucinations)
        hallucination_count += n_hallucinations
        if n_hallucinations > 0:
            examples_with_hallucinations += 1
        # рубрика проходит, только если 0 галлюцинаций И метрика есть И без канцелярита
        if n_hallucinations == 0 and verdict.has_metric and verdict.no_cliche:
            passed += 1
        else:
            fail_rubric += 1

    return CoverMetrics(
        gen_model=gen_model,
        judge_model=judge_model,
        total=len(examples),
        passed=passed,
        fail_length=fail_length,
        fail_addresses=fail_addresses,
        fail_rubric=fail_rubric,
        hallucination_count=hallucination_count,
        examples_with_hallucinations=examples_with_hallucinations,
        judge_errors=judge_errors,
    )
