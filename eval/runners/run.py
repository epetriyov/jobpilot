"""Eval-раннер (PLAN.md §5, TEST_CASES.md приложение).

`make eval CONTEXT=<name>` → метрики в stdout + отчёт eval/reports/<name>_<date>.md.
Пороги зашиты в раннеры как assertions; провал порога → ненулевой код возврата.

Этап 0: контекст `smoke` гоняется на фейковом провайдере (без ключей/сети) —
проверяет, что LLM-слой отдаёт валидную схему на каждый пример. Полноценные
контексты (relevance, mail_classify, …) добавляются на своих этапах.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.adapters.llm.fake import FakeLlm
from app.config import Settings
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "eval" / "datasets"
REPORTS = ROOT / "eval" / "reports"

# Пороги контекстов (TEST_CASES.md). smoke — служебный, порог 1.0.
# relevance ([R-E1]): precision ≥0.7 И recall ≥0.7 — проверяется отдельно (не pass-rate).
THRESHOLDS: dict[str, float] = {"smoke": 1.0, "relevance": 0.7}


class Score(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200)


@dataclass
class EvalResult:
    context: str
    version: str
    total: int
    passed: int
    threshold: float
    records: list[LlmCallRecord] = field(default_factory=list)

    @property
    def metric(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def ok(self) -> bool:
        return self.metric >= self.threshold


class _Recorder:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, call: LlmCallRecord) -> None:
        self.records.append(call)


def latest_version(context: str) -> tuple[str, Path]:
    ctx_dir = DATASETS / context
    files = sorted(ctx_dir.glob("v*.jsonl"))
    if not files:
        raise SystemExit(f"нет датасета для контекста '{context}' в {ctx_dir}")
    return files[-1].stem, files[-1]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run_smoke(examples: list[dict], recorder: _Recorder) -> int:
    """Прогоняет фейковый скоринг; пример «прошёл», если получена валидная схема."""
    passed = 0
    pv = PromptVersion(purpose="scoring", version=1)
    for ex in examples:
        llm = FakeLlm(recorder=recorder, responses=['{"score": 55, "reason": "eval smoke"}'])
        result = await llm.complete(
            purpose="scoring",
            prompt_version=pv,
            system="scoring",
            data=ex["input"]["vacancy_text"],
            response_model=Score,
        )
        if result is not None:
            passed += 1
    return passed


RUNNERS = {"smoke": run_smoke}


async def evaluate(context: str) -> EvalResult:
    version, path = latest_version(context)
    examples = load(path)
    recorder = _Recorder()
    runner = RUNNERS.get(context)
    if runner is None:
        raise SystemExit(f"раннер для контекста '{context}' ещё не реализован")
    passed = await runner(examples, recorder)
    return EvalResult(
        context=context,
        version=version,
        total=len(examples),
        passed=passed,
        threshold=THRESHOLDS.get(context, 1.0),
        records=recorder.records,
    )


async def evaluate_relevance(model_b: str | None) -> int:
    """[R-E1] Контекст relevance: P/R/F1 (+сравнение MODEL_B). Возврат — код выхода."""
    from eval.runners.relevance import _Recorder as RelRecorder
    from eval.runners.relevance import score_dataset

    version, path = latest_version("relevance")
    examples = load(path)
    settings = Settings.load()
    use_real = settings.resolved_llm_mode() == "real" and os.environ.get("EVAL_FAKE") != "1"
    threshold = settings.digest_score_threshold
    model_a = settings.llm_model_scoring

    rec_a = RelRecorder()
    metrics_a = await score_dataset(
        examples,
        model=model_a,
        recorder=rec_a,
        use_real=use_real,
        settings=settings,
        threshold=threshold,
    )
    metrics_b = None
    if model_b:
        rec_b = RelRecorder()
        metrics_b = await score_dataset(
            examples,
            model=model_b,
            recorder=rec_b,
            use_real=use_real,
            settings=settings,
            threshold=threshold,
        )

    ok = metrics_a.precision >= 0.7 and metrics_a.recall >= 0.7
    report = _write_relevance_report(
        version, len(_dedup_count(examples)), use_real, metrics_a, metrics_b, rec_a.records
    )
    print(
        f"[eval:relevance] model={metrics_a.model} P={metrics_a.precision:.3f} "
        f"R={metrics_a.recall:.3f} F1={metrics_a.f1:.3f} -> {'PASS' if ok else 'FAIL'}\n"
        f"report: {report.relative_to(ROOT)}"
    )
    if metrics_b:
        print(
            f"[eval:relevance] MODEL_B={metrics_b.model} F1={metrics_b.f1:.3f} "
            f"ΔF1={metrics_b.f1 - metrics_a.f1:+.3f}"
        )
    return 0 if ok else 1


def _dedup_count(examples: list[dict]) -> dict:  # type: ignore[type-arg]
    return {ex["id"]: ex for ex in examples}


def _write_relevance_report(version, total, use_real, a, b, records) -> Path:  # type: ignore[no-untyped-def]
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out = REPORTS / f"relevance_{stamp}.md"
    cost = sum(r.cost_usd for r in records)
    provider = "real (OpenRouter)" if use_real else "fake (стаб)"
    lines = [
        f"# Eval report: relevance ({version})",
        "",
        f"- **Дата**: {stamp} · **Провайдер**: {provider} · **Примеров (уникальных)**: {total}",
        "- **Критерий [R-E1]**: precision ≥0.7 И recall ≥0.7",
        f"- **Стоимость прогона**: ${cost:.6f}",
        "",
        "| Модель | Precision | Recall | F1 | TP | FP | FN | TN |",
        "|---|---|---|---|---|---|---|---|",
        f"| {a.model} | {a.precision:.3f} | {a.recall:.3f} | {a.f1:.3f} "
        f"| {a.tp} | {a.fp} | {a.fn} | {a.tn} |",
    ]
    if b:
        lines.append(
            f"| {b.model} | {b.precision:.3f} | {b.recall:.3f} | {b.f1:.3f} "
            f"| {b.tp} | {b.fp} | {b.fn} | {b.tn} |"
        )
        lines += [
            "",
            f"**ΔF1 (B−A)** = {b.f1 - a.f1:+.3f} — |ΔF1| ≤ 0.05 → остаёмся на A (Flash-Lite).",
        ]
    status = "✅ PASS" if (a.precision >= 0.7 and a.recall >= 0.7) else "❌ FAIL"
    lines += ["", f"**Статус**: {status}"]
    if total < 30:
        lines += [
            "",
            f"> ⚠️ Примеров {total} < 30 — датасет не добран ([R-E1]); метрики предварительные.",
        ]
    out.write_text("\n".join(lines) + "\n")
    return out


def write_report(result: EvalResult) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out = REPORTS / f"{result.context}_{stamp}.md"
    total_cost = sum(r.cost_usd for r in result.records)
    total_tokens = sum(r.input_tokens + r.output_tokens for r in result.records)
    out.write_text(
        f"""# Eval report: {result.context}

- **Датасет**: {result.context}/{result.version}.jsonl ({result.total} примеров)
- **Дата**: {stamp}
- **Метрика (pass rate)**: {result.metric:.3f}
- **Порог**: {result.threshold:.3f}
- **Статус**: {"✅ PASS" if result.ok else "❌ FAIL"}
- **LLM-вызовов**: {len(result.records)} · токенов: {total_tokens} · стоимость: ${total_cost:.6f}

> smoke — служебный контекст этапа 0 (фейковый провайдер, без ключей). Реальные
> контексты (relevance и др.) добавляются на своих этапах с датасетами и порогами.
"""
    )
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--model-b", default=os.environ.get("MODEL_B"))
    args = parser.parse_args()

    if args.context == "relevance":
        code = await evaluate_relevance(args.model_b)
        raise SystemExit(code)

    result = await evaluate(args.context)
    report = write_report(result)
    print(
        f"[eval:{result.context}] pass_rate={result.metric:.3f} "
        f"threshold={result.threshold:.3f} -> {'PASS' if result.ok else 'FAIL'}\n"
        f"report: {report.relative_to(ROOT)}"
    )
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
