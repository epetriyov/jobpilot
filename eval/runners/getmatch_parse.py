"""Eval-контекст `getmatch_parse` ([S-E1], T410): accuracy парсера GetMatch.

Golden `tests/golden/getmatch/offers.json` (полный ответ /api/offers) → parse →
сверка ключевых полей (title/company/url) с эталоном по external_id. Порог ≥0.95.
Чистый eval без сети/LLM — годится для CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.adapters.getmatch.parser import parse_getmatch_offers

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "getmatch"
KEY_FIELDS = ("title", "company", "url")


@dataclass
class GetMatchMetrics:
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def evaluate_getmatch() -> GetMatchMetrics:
    payload = (GOLDEN / "offers.json").read_text(encoding="utf-8")
    expected = json.loads((GOLDEN / "offers.expected.json").read_text(encoding="utf-8"))
    actual_by_id = {v.source_ref.external_id: v for v in parse_getmatch_offers(payload)}

    correct = 0
    for exp in expected:
        got = actual_by_id.get(exp["external_id"])
        if got is None:
            continue
        shape = {"title": got.title, "company": got.company, "url": got.url}
        if all(shape[f] == exp[f] for f in KEY_FIELDS):
            correct += 1
    return GetMatchMetrics(total=len(expected), correct=correct)
