"""Eval-контекст `invite_rubric` ([N-E1], T311): LLM-as-judge качества инвайтов.

Датасет — пары (роль адресата, компания) из конфиг-списка. Для каждой пары:
  1) генерируем инвайт (purpose="invite", промпт invite_v1) — как в BuildInviteBatch;
  2) детерминированные проверки: длина ≤300 (N2) и упоминание компании (персонализация);
  3) LLM-судья (purpose="judge") оценивает тон под роль и отсутствие штампов.
Пример «прошёл», если код-проверки И судья дали ОК. Порог pass ≥0.9.

Провайдер: real (OpenRouter) при ключе и без EVAL_FAKE; иначе детерминированный стаб
(судья в fake всегда «passes» — fake проверяет валидность схемы, не качество).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.adapters.llm.fake import FakeLlm, stub_invite_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.config import Settings
from app.domain.networking import InviteText
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord, LlmPort

INVITE_PV = PromptVersion(purpose="invite", version=2)
JUDGE_PV = PromptVersion(purpose="judge", version=1)

# Рубрика судьи (eval-локальная; не продовый промпт). Текст инвайта — в блоке данных.
JUDGE_SYSTEM = (
    "Ты — строгий ревьюер коротких LinkedIn-инвайтов. В блоке данных: роль адресата, "
    "компания и текст инвайта. Оцени по критериям:\n"
    "1) тон уместен роли (CTO — про инженерию; HRBP/рекрутер — про опыт и интерес к команде);\n"
    "2) нет штампов («I came across your profile», «взаимовыгодное сотрудничество») и "
    "просьб о работе в лоб;\n"
    "3) упомянута компания, текст персонализирован, вежлив.\n"
    'Верни строгий JSON: {"passes": <bool>, "reason": <строка ≤200>}. '
    "passes=true только если ВСЕ критерии выполнены."
)


class JudgeVerdict(BaseModel):
    passes: bool
    reason: str = Field(max_length=200)


def _stub_judge_response(_data: str) -> str:
    return json.dumps({"passes": True, "reason": "fake: схема валидна"}, ensure_ascii=False)


class _Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


JUDGE_ATTEMPTS = 3  # gemium-flash иногда обрывает JSON → добираем повтором (инфра, не рубрика)


@dataclass
class InviteMetrics:
    gen_model: str
    judge_model: str
    total: int
    passed: int
    fail_length: int
    fail_company: int
    fail_judge: int
    judge_errors: int  # судья не отдал валидную схему за все попытки — инфра, вне знаменателя

    @property
    def evaluable(self) -> int:
        return self.total - self.judge_errors

    @property
    def pass_rate(self) -> float:
        """Доля прошедших рубрику среди оценённых (инфра-сбои судьи исключены)."""
        return self.passed / self.evaluable if self.evaluable else 0.0


def _llms(
    recorder: _Recorder, *, use_real: bool, settings: Settings
) -> tuple[LlmPort, LlmPort, str, str]:
    if use_real:
        llm = InstructorOpenRouterLlm(settings=settings, recorder=recorder)
        return llm, llm, settings.llm_model_invite, settings.llm_model_judge
    gen = FakeLlm(recorder=recorder, model="fake/invite", response_factory=stub_invite_response)
    judge = FakeLlm(recorder=recorder, model="fake/judge", response_factory=_stub_judge_response)
    return gen, judge, "fake/invite", "fake/judge"


async def judge_dataset(
    examples: list[dict],  # type: ignore[type-arg]
    *,
    recorder: _Recorder,
    use_real: bool,
    settings: Settings,
) -> InviteMetrics:
    gen_llm, judge_llm, gen_model, judge_model = _llms(
        recorder, use_real=use_real, settings=settings
    )
    invite_system = load_system_prompt("invite", INVITE_PV.version)
    passed = fail_length = fail_company = fail_judge = judge_errors = 0
    for ex in examples:
        role, company = ex["input"]["role"], ex["input"]["company"]
        draft = await gen_llm.complete(
            purpose="invite",
            prompt_version=INVITE_PV,
            system=invite_system,
            data=f"Роль адресата: {role}\nКомпания: {company}",
            response_model=InviteText,
        )
        if draft is None or len(draft.text) > 300:
            fail_length += 1
            continue
        if company.lower() not in draft.text.lower():
            fail_company += 1
            continue
        verdict = None
        for _ in range(JUDGE_ATTEMPTS):  # добор при обрыве JSON судьи (инфра-флап)
            verdict = await judge_llm.complete(
                purpose="judge",
                prompt_version=JUDGE_PV,
                system=JUDGE_SYSTEM,
                data=f"Роль адресата: {role}\nКомпания: {company}\nТекст инвайта:\n{draft.text}",
                response_model=JudgeVerdict,
            )
            if verdict is not None:
                break
        if verdict is None:
            judge_errors += 1  # судья не смог оценить — вне знаменателя pass-rate
        elif verdict.passes:
            passed += 1
        else:
            fail_judge += 1
    return InviteMetrics(
        gen_model,
        judge_model,
        len(examples),
        passed,
        fail_length,
        fail_company,
        fail_judge,
        judge_errors,
    )
