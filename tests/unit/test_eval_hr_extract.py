"""T6G-3: eval hr_extract в fake-режиме — детерминированный стаб, accuracy ≥0.9.

[C-E1]: accuracy по дате и ссылке ≥0.9 на ≥15 обезличенных HR-сообщениях. В fake
стаб парсит дату/ссылку из текста детерминированно → на согласованном датасете
accuracy = 1.0. Реальный прогон — на OpenRouter после кредов.
"""

import json
from pathlib import Path

import pytest

from app.config import Settings
from eval.runners.hr_extract import _Recorder, extract_dataset

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test",
    "POSTGRES_DSN": "postgresql+psycopg://u:p@localhost:5432/db",
}
_ROOT = Path(__file__).resolve().parents[2]
_DATASET = _ROOT / "eval" / "datasets" / "hr_extract" / "v1.jsonl"


def _fake_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LLM_MODE", "fake")
    return Settings.load(env_file=None)


def _load_dataset() -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line) for line in _DATASET.read_text().splitlines() if line.strip()]


def test_dataset_has_at_least_15_messages() -> None:
    assert len(_load_dataset()) >= 15  # [C-E1] минимум датасета


async def test_hr_extract_fake_meets_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _fake_settings(monkeypatch)
    examples = _load_dataset()
    rec = _Recorder()

    m = await extract_dataset(examples, recorder=rec, use_real=False, settings=settings)

    assert m.total == len(examples)
    # детерминированный стаб → точное совпадение даты и ссылки
    assert m.date_accuracy >= 0.9
    assert m.url_accuracy >= 0.9
    assert m.ok is True
    # честный учёт llm_call на каждый пример (O1)
    assert len(rec.records) == m.total
    assert all(r.purpose == "hr_extract" for r in rec.records)
