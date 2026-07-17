"""Eval-контекст `relevance` ([R-E1], T119): precision/recall/F1 скоринга.

Датасет — размеченные 👍/👎 вакансии (append-only; дубли по id → последний вердикт).
verdict_pred = relevant, если score ≥ порога дайджеста. Пороги: precision ≥0.7 и recall ≥0.7.
Сравнение моделей (MODEL_B) → ΔF1 в отчёте (|ΔF1| ≤ 0.05 → остаёмся на текущей).

Провайдер: real (OpenRouter) при наличии ключа и без --fake; иначе детерминированный стаб.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.adapters.llm.fake import FakeLlm, stub_scoring_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.config import Settings
from app.domain.relevance import LlmScore
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord, LlmPort

PV = PromptVersion(purpose="scoring", version=1)
PROFILE_PATH = Path(__file__).resolve().parents[2] / "resumes" / "resume_em.md"


class _Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


@dataclass
class Metrics:
    model: str
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int


def _system_prompt() -> str:
    prompt = load_system_prompt("scoring", PV.version)
    if PROFILE_PATH.exists():
        prompt += "\n\n## Профиль кандидата (резюме)\n" + PROFILE_PATH.read_text()[:4000]
    return prompt


def _make_llm(model: str, recorder: _Recorder, *, use_real: bool, settings: Settings) -> LlmPort:
    if use_real:
        return InstructorOpenRouterLlm(
            settings=settings, recorder=recorder, purpose_models={"scoring": model}
        )
    return FakeLlm(recorder=recorder, model=model, response_factory=stub_scoring_response)


def _dedup_last(examples: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    by_id: dict[str, dict] = {}  # type: ignore[type-arg]
    for ex in examples:
        by_id[ex["id"]] = ex
    return list(by_id.values())


async def score_dataset(
    examples: list[dict],  # type: ignore[type-arg]
    *,
    model: str,
    recorder: _Recorder,
    use_real: bool,
    settings: Settings,
    threshold: int,
) -> Metrics:
    llm = _make_llm(model, recorder, use_real=use_real, settings=settings)
    system = _system_prompt()
    tp = fp = fn = tn = 0
    for ex in _dedup_last(examples):
        text = ex["input"].get("vacancy_text") or ex["input"].get("title", "")
        result = await llm.complete(
            purpose="scoring",
            prompt_version=PV,
            system=system,
            data=text,
            response_model=LlmScore,
        )
        pred_relevant = result is not None and result.score >= threshold
        gold_relevant = ex["expected"]["verdict"] == "relevant"
        if gold_relevant and pred_relevant:
            tp += 1
        elif not gold_relevant and pred_relevant:
            fp += 1
        elif gold_relevant and not pred_relevant:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return Metrics(model, precision, recall, f1, tp, fp, fn, tn)
