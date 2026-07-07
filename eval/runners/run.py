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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.adapters.llm.fake import FakeLlm
from app.domain.shared import PromptVersion
from app.ports.llm import LlmCallRecord

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "eval" / "datasets"
REPORTS = ROOT / "eval" / "reports"

# Пороги контекстов (TEST_CASES.md). smoke — служебный, порог 1.0.
THRESHOLDS: dict[str, float] = {"smoke": 1.0}


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
    args = parser.parse_args()

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
