"""Домен relevance: R2 (схема Score), R3 few-shot [R-U2], R4 отбор в дайджест [R-U3]."""

import pytest
from pydantic import ValidationError

from app.domain.relevance import LlmScore, Score, build_few_shot, select_for_digest
from app.domain.shared import Source, SourceRef
from app.ports.repositories import LabeledVacancy


def make_score(value: int) -> Score:
    return Score(value=value, reason="r", prompt_version="scoring_v1", model="m")


class TestScoreSchema:
    def test_valid_bounds(self) -> None:
        assert make_score(0).value == 0
        assert make_score(100).value == 100

    def test_out_of_range_rejected(self) -> None:
        """R2: {"score": 150} невалиден по схеме."""
        with pytest.raises(ValidationError):
            make_score(150)
        with pytest.raises(ValidationError):
            make_score(-1)

    def test_reason_max_200(self) -> None:
        with pytest.raises(ValidationError):
            Score(value=50, reason="x" * 201, prompt_version="v", model="m")


class TestLlmScoreVerbosity:
    """R2 (2026-07-17): многословный reason реального LLM не роняет вакансию —
    терпим до 2000, обрезаем до 200. score вне диапазона по-прежнему реджект."""

    def test_long_reason_accepted_and_truncated(self) -> None:
        s = LlmScore(score=80, reason="ц" * 900)
        assert len(s.to_reason()) == 200

    def test_score_out_of_range_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LlmScore(score=150, reason="ok")


class TestSelectForDigest:
    """[R-U3] Given 60 вакансий, threshold=60 → топ-50 по убыванию, все ≥60."""

    def test_top_50_sorted_above_threshold(self) -> None:
        # 60 вакансий со скорами 60..89 — все проходят порог, но в дайджест только топ-50
        scored = [(f"hh:{i}", make_score(60 + i // 2)) for i in range(60)]

        selected = select_for_digest(scored, threshold=60, max_items=50)

        assert len(selected) == 50
        values = [s.value for _, s in selected]
        assert values == sorted(values, reverse=True)
        assert all(v >= 60 for v in values)

    def test_below_threshold_excluded(self) -> None:
        scored = [("hh:1", make_score(59)), ("hh:2", make_score(60))]
        selected = select_for_digest(scored, threshold=60, max_items=50)
        assert [ref for ref, _ in selected] == ["hh:2"]

    def test_empty_input(self) -> None:
        assert select_for_digest([], threshold=60, max_items=50) == []


def _label(i: int, verdict: str) -> LabeledVacancy:
    return LabeledVacancy(
        source_ref=SourceRef(source=Source.HH, external_id=str(i)),
        title=f"Vacancy {i}",
        company="Acme",
        url=f"https://hh.ru/{i}",
        description_text=f"Описание вакансии {i} " + "х" * 1000,
        verdict=verdict,  # type: ignore[arg-type]
    )


class TestBuildFewShot:
    """[R-U2] 3 размеченных → все 3; 25 → ровно 10 (R3)."""

    def test_three_labels_all_used(self) -> None:
        examples = build_few_shot([_label(i, "relevant") for i in range(3)])
        assert len(examples) == 3

    def test_capped_at_ten(self) -> None:
        examples = build_few_shot([_label(i, "relevant") for i in range(25)], limit=10)
        assert len(examples) == 10

    def test_verdict_anchors(self) -> None:
        relevant, irrelevant = build_few_shot([_label(1, "relevant"), _label(2, "irrelevant")])
        assert '"score": 85' in relevant[1]
        assert '"score": 15' in irrelevant[1]

    def test_text_truncated(self) -> None:
        examples = build_few_shot([_label(1, "relevant")], text_limit=100)
        user_text = examples[0][0]
        assert len(user_text) <= 200  # текст урезан (плюс служебная обвязка)
