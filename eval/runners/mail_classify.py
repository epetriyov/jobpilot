"""Eval-контекст `mail_classify` ([M-E1], T212): accuracy классификации «про работу?».

Датасет — мок-корпус писем (input: sender/subject/body; expected: is_job, critical).
Прогон повторяет продовый путь ClassifyInbox: prefilter (без LLM) → на ветке "llm"
классификация LLM (MailVerdict). Метрики:
  - accuracy ≥ 0.9;
  - FN на critical-письмах (оффер/интервью) = 0 — блокер: пропуск оффера недопустим.

Провайдер: real (OpenRouter) при ключе и без EVAL_FAKE; иначе детерминированный стаб.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.llm.fake import FakeLlm, stub_mail_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.config import Settings
from app.domain.correspondence import MailVerdict, prefilter
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord, LlmPort

PV = PromptVersion(purpose="mail_classify", version=1)


class _Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


@dataclass
class MailMetrics:
    model: str
    total: int
    correct: int
    fn_critical: int
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def _make_llm(model: str, recorder: _Recorder, *, use_real: bool, settings: Settings) -> LlmPort:
    if use_real:
        # продовый путь использует purpose="summary" (prompt — mail_classify_v1)
        return InstructorOpenRouterLlm(
            settings=settings, recorder=recorder, purpose_models={"summary": model}
        )
    return FakeLlm(recorder=recorder, model=model, response_factory=stub_mail_response)


async def _predict_is_job(ex: dict, llm: LlmPort, system: str) -> bool:  # type: ignore[type-arg]
    """Повторяет ветвление ClassifyInbox: drop→False, linkedin/hidden→surfaced(True),
    llm→вердикт (None-фолбэк = письмо показано, не считается пропуском оффера)."""
    inp = ex["input"]
    decision = prefilter(sender=inp["sender"], subject=inp["subject"])
    if decision == "drop":
        return False
    if decision in ("linkedin", "hidden"):
        return True
    data = f"From: {inp['sender']}\nSubject: {inp['subject']}\n\n{inp['body']}"
    verdict = await llm.complete(
        purpose="summary",
        prompt_version=PV,
        system=system,
        data=data,
        response_model=MailVerdict,
    )
    if verdict is None:
        return True  # M2-фолбэк: письмо не теряется
    return verdict.is_job


async def classify_dataset(
    examples: list[dict],  # type: ignore[type-arg]
    *,
    model: str,
    recorder: _Recorder,
    use_real: bool,
    settings: Settings,
) -> MailMetrics:
    llm = _make_llm(model, recorder, use_real=use_real, settings=settings)
    system = load_system_prompt("mail_classify", PV.version)
    tp = fp = fn = tn = 0
    correct = 0
    fn_critical = 0
    for ex in examples:
        pred = await _predict_is_job(ex, llm, system)
        gold = ex["expected"]["is_job"]
        if pred == gold:
            correct += 1
        if gold and pred:
            tp += 1
        elif not gold and pred:
            fp += 1
        elif gold and not pred:
            fn += 1
            if ex["expected"].get("critical"):
                fn_critical += 1
        else:
            tn += 1
    return MailMetrics(model, len(examples), correct, fn_critical, tp, fp, fn, tn)
