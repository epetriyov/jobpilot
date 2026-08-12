"""Юнит-тесты рендера аналитики (T6C): текст /stats, /costs и карточка /review."""

from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.telegram.analytics_cards import (
    build_review_keyboard,
    parse_review_callback,
    render_costs,
    render_funnel,
    render_review_candidate,
    render_review_summary,
)
from app.application.funnel_stats import FunnelReport
from app.application.report_costs import CostReport
from app.application.review_agreement import ReviewCandidate, ReviewSummary
from app.domain.shared import Source, SourceRef
from app.ports.repositories import CostTotals


def _funnel() -> FunnelReport:
    return FunnelReport(
        counts={"new": 2, "applied": 3, "interview": 4, "offer": 1, "rejected": 2},
        total=12,
        reached_applied=8,
        reached_interview=5,
        reached_offer=1,
        applied_rate=8 / 12,
        interview_rate=5 / 8,
        offer_rate=1 / 5,
        rejected=2,
        vacancies_total=100,
        vacancies_scored=40,
        labeled_relevant=12,
        labeled_irrelevant=8,
    )


def test_render_funnel_has_counts_and_conversions() -> None:
    text = render_funnel(_funnel())
    assert "Воронка" in text
    assert "12" in text  # total
    assert "%" in text  # конверсии в процентах
    assert "100" in text and "40" in text  # вакансии
    assert "12" in text and "8" in text  # разметка


def test_render_costs_shows_usd_and_tokens() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    report = CostReport(
        days=30,
        since=now,
        until=now,
        totals=CostTotals(
            total_usd=1.234567,
            input_tokens=1000,
            output_tokens=500,
            calls=7,
            by_purpose={"scoring": 1.0, "cover": 0.234567},
        ),
    )
    text = render_costs(report)
    assert "$" in text
    assert "30" in text  # период
    assert "1500" in text or "1 500" in text  # суммарные токены
    assert "scoring" in text  # разбивка по назначению


def test_review_keyboard_and_parse_roundtrip() -> None:
    kb = build_review_keyboard()
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "rev:up" in datas and "rev:down" in datas
    assert parse_review_callback("rev:up") == "relevant"
    assert parse_review_callback("rev:down") == "irrelevant"


def test_parse_review_callback_rejects_garbage() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse_review_callback("noise")


def test_render_review_candidate_hides_model_verdict() -> None:
    cand = ReviewCandidate(
        source_ref=SourceRef(source=Source.HH, external_id="42"),
        title="EM",
        company="Acme",
        url="https://hh.ru/42",
        description_text="описание",
        score=80,
        model_verdict="relevant",
    )
    text = render_review_candidate(cand, index=0, total=10)
    assert "EM" in text and "Acme" in text
    assert "1/10" in text  # прогресс
    # вердикт модели скрыт, чтобы не смещать оценку владельца
    assert "relevant" not in text


def test_render_review_summary() -> None:
    text = render_review_summary(ReviewSummary.of(agreed=7, total=10))
    assert "70" in text  # 70%
    assert "10" in text
