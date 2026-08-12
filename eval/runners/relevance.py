"""Eval-контекст `relevance` ([R-E1], T119): precision/recall/F1 скоринга.

Датасет — размеченные 👍/👎 вакансии (append-only; дубли по id → последний вердикт).
verdict_pred = relevant, если score ≥ порога дайджеста. Пороги: precision ≥0.7 и recall ≥0.7.
Сравнение моделей (MODEL_B) → ΔF1 в отчёте (|ΔF1| ≤ 0.05 → остаёмся на текущей).

Провайдер: real (OpenRouter) при наличии ключа и без --fake; иначе детерминированный стаб.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.adapters.embeddings.fake import FakeEmbedder
from app.adapters.embeddings.openrouter import OpenRouterEmbedder
from app.adapters.llm.fake import FakeLlm, stub_scoring_response
from app.adapters.llm.instructor_openrouter import InstructorOpenRouterLlm
from app.adapters.llm.prompts import load_system_prompt
from app.config import Settings
from app.domain.relevance import LabeledVacancy, LlmScore, VacancySnapshot, build_few_shot
from app.domain.shared import PromptVersion, Source, SourceRef
from app.ports.embeddings import EmbeddingPort
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


# --- [R-E2] Сравнение few-shot-селекторов: semantic vs «последние N» ---------------

SelectorKind = Literal["recent", "semantic"]


@dataclass
class SelectorMetrics:
    selector: SelectorKind
    total: int
    agreement: float  # доля совпадений предсказания с эталоном (agreement rate)
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int


def make_embedder(recorder: _Recorder, *, use_real: bool, settings: Settings) -> EmbeddingPort:
    if use_real:
        return OpenRouterEmbedder(settings=settings, recorder=recorder)
    return FakeEmbedder(recorder=recorder)


def _labeled_from_ex(ex: dict) -> LabeledVacancy:  # type: ignore[type-arg]
    inp = ex["input"]
    snap = VacancySnapshot(
        source_ref=SourceRef(source=Source.MANUAL, external_id=str(ex["id"])),
        title=inp.get("title", ""),
        company=inp.get("company", ""),
        url="",
        description_text=inp.get("vacancy_text") or inp.get("title", ""),
    )
    return LabeledVacancy(**snap.model_dump(), verdict=ex["expected"]["verdict"])


def _text_of(labeled: LabeledVacancy) -> str:
    return f"{labeled.title} — {labeled.company}\n{labeled.description_text}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


async def _few_shot_for(
    target: LabeledVacancy,
    pool: list[LabeledVacancy],
    *,
    selector: SelectorKind,
    limit: int,
    text_limit: int,
    embedder: EmbeddingPort,
    pool_embeddings: dict[str, list[float]],
) -> list[tuple[str, str]]:
    others = [p for p in pool if p.source_ref.external_id != target.source_ref.external_id]
    if selector == "recent":
        chosen = others[-limit:]
    else:
        q = await embedder.embed(_text_of(target))
        ranked = sorted(
            others,
            key=lambda p: _cosine(q, pool_embeddings[p.source_ref.external_id]),
            reverse=True,
        )
        chosen = ranked[:limit]
    return build_few_shot(chosen, limit=limit, text_limit=text_limit)


async def score_dataset_with_selector(
    examples: list[dict],  # type: ignore[type-arg]
    *,
    selector: SelectorKind,
    model: str,
    recorder: _Recorder,
    embedder: EmbeddingPort,
    use_real: bool,
    settings: Settings,
    threshold: int,
) -> SelectorMetrics:
    """Скоринг датасета с few-shot из соседей по выбранной стратегии; agreement rate + F1."""
    llm = _make_llm(model, recorder, use_real=use_real, settings=settings)
    system = _system_prompt()
    pool = [_labeled_from_ex(ex) for ex in _dedup_last(examples)]

    pool_embeddings: dict[str, list[float]] = {}
    if selector == "semantic":
        for p in pool:
            pool_embeddings[p.source_ref.external_id] = await embedder.embed(_text_of(p))

    tp = fp = fn = tn = 0
    correct = 0
    for target in pool:
        few_shot = await _few_shot_for(
            target,
            pool,
            selector=selector,
            limit=settings.fewshot_limit,
            text_limit=settings.fewshot_text_limit,
            embedder=embedder,
            pool_embeddings=pool_embeddings,
        )
        result = await llm.complete(
            purpose="scoring",
            prompt_version=PV,
            system=system,
            data=_text_of(target),
            response_model=LlmScore,
            few_shot=few_shot,
        )
        pred_relevant = result is not None and result.score >= threshold
        gold_relevant = target.verdict == "relevant"
        if pred_relevant == gold_relevant:
            correct += 1
        if gold_relevant and pred_relevant:
            tp += 1
        elif not gold_relevant and pred_relevant:
            fp += 1
        elif gold_relevant and not pred_relevant:
            fn += 1
        else:
            tn += 1
    total = len(pool)
    agreement = correct / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return SelectorMetrics(selector, total, agreement, f1, tp, fp, fn, tn)
