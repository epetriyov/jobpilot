"""T6E-5: eval cover_letter в fake-режиме — валидная схема, hallucinations=0, PASS.

Fake-судья всегда «hallucinations=[]» (проверяет валидность схемы, не факты) — это
CI-eval до реального OpenRouter (M-E2). Реальный fact-check — на real-провайдере.
"""

import json
from pathlib import Path

import pytest

from app.config import Settings
from eval.runners.cover_letter import _Recorder, judge_dataset

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test",
    "POSTGRES_DSN": "postgresql+psycopg://u:p@localhost:5432/db",
}
_ROOT = Path(__file__).resolve().parents[2]
_DATASET = _ROOT / "eval" / "datasets" / "cover_letter" / "v1.jsonl"


def _fake_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LLM_MODE", "fake")
    return Settings.load(env_file=None)


def _load_dataset() -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line) for line in _DATASET.read_text().splitlines() if line.strip()]


def test_dataset_has_at_least_10_vacancies() -> None:
    assert len(_load_dataset()) >= 10  # [M-E2] минимум датасета


async def test_cover_eval_fake_passes_with_zero_hallucinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _fake_settings(monkeypatch)
    examples = _load_dataset()
    rec = _Recorder()

    m = await judge_dataset(examples, recorder=rec, use_real=False, settings=settings)

    assert m.total == len(examples)
    assert m.hallucination_count == 0  # блокер [M-E2]
    assert m.fail_length == 0  # стаб-письмо ≤2000
    assert m.fail_addresses == 0  # стаб упоминает вакансию/компанию
    assert m.rubric_pass_rate == 1.0
    assert m.ok is True
    # честный учёт llm_call на генерацию и на судью (O1)
    assert len(rec.records) >= m.total * 2


async def test_hallucination_is_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Любой неподтверждённый факт (judge вернул hallucinations) → ok=False (блокер)."""
    from eval.runners import cover_letter as mod

    settings = _fake_settings(monkeypatch)

    def _lying_judge(_data: str) -> str:
        return json.dumps(
            {
                "hallucinations": ["выдуманная метрика: SLA 99.9%"],
                "has_metric": True,
                "no_cliche": True,
                "reason": "fake: 1 галлюцинация",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(mod, "_stub_cover_judge_response", _lying_judge)
    rec = _Recorder()
    m = await judge_dataset(_load_dataset()[:3], recorder=rec, use_real=False, settings=settings)

    assert m.hallucination_count == 3
    assert m.ok is False  # блокер сработал
