"""Юнит-тесты бот-хендлеров аналитики (T6C): /stats, /costs и диалог /review.

Хендлеры тонкие: разбор апдейта → services (use case) → рендер. Здесь — на фейках
Services и FSMContext, без БД и сети.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.application.funnel_stats import FunnelReport
from app.application.report_costs import CostReport
from app.application.review_agreement import RecordedVerdict, ReviewCandidate
from app.bot.handlers import ReviewFlow, cmd_costs, cmd_review, cmd_stats, on_review
from app.domain.shared import Source, SourceRef
from app.ports.repositories import CostTotals


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []
        self.markups: list[Any] = []

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.replies.append(text)
        self.markups.append(reply_markup)


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answered: list[str] = []
        self.message = FakeMessage("")

    async def answer(self, text: str = "", **_: Any) -> None:
        self.answered.append(text)


class FakeState:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.state: Any = None

    async def set_state(self, state: Any) -> None:
        self.state = state

    async def update_data(self, **kwargs: Any) -> None:
        self._data.update(kwargs)

    async def get_data(self) -> dict[str, Any]:
        return dict(self._data)

    async def clear(self) -> None:
        self._data.clear()
        self.state = None


def _funnel() -> FunnelReport:
    return FunnelReport(
        counts={"new": 1, "applied": 0, "interview": 0, "offer": 0, "rejected": 0},
        total=1,
        reached_applied=0,
        reached_interview=0,
        reached_offer=0,
        applied_rate=0.0,
        interview_rate=0.0,
        offer_rate=0.0,
        rejected=0,
        vacancies_total=10,
        vacancies_scored=4,
        labeled_relevant=2,
        labeled_irrelevant=1,
    )


def _cost_report(days: int) -> CostReport:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    return CostReport(
        days=days,
        since=now,
        until=now,
        totals=CostTotals(
            total_usd=0.5, input_tokens=100, output_tokens=50, calls=3, by_purpose={"scoring": 0.5}
        ),
    )


def _candidate(external_id: str, model_verdict: str) -> ReviewCandidate:
    return ReviewCandidate(
        source_ref=SourceRef(source=Source.HH, external_id=external_id),
        title=f"EM {external_id}",
        company="Acme",
        url=f"https://hh.ru/{external_id}",
        description_text="описание",
        score=80,
        model_verdict=model_verdict,  # type: ignore[arg-type]
    )


class FakeServices:
    def __init__(self) -> None:
        self.cost_days: list[int] = []
        self.review_candidates: list[ReviewCandidate] = []
        self.recorded: list[tuple[str, str]] = []
        self._agree = True

    async def funnel_stats(self) -> FunnelReport:
        return _funnel()

    async def report_costs(self, days: int) -> CostReport:
        self.cost_days.append(days)
        return _cost_report(days)

    async def start_review(self, n: int) -> list[ReviewCandidate]:
        return self.review_candidates[:n]

    async def record_review_verdict(
        self, candidate: ReviewCandidate, verdict: str
    ) -> RecordedVerdict:
        self.recorded.append((candidate.source_ref.external_id, verdict))
        return RecordedVerdict(
            source_ref=candidate.source_ref,
            owner_verdict=verdict,  # type: ignore[arg-type]
            model_verdict=candidate.model_verdict,
            agreed=self._agree,
            recorded_label=not self._agree,
        )


async def test_cmd_stats_renders_funnel() -> None:
    msg = FakeMessage("/stats")
    await cmd_stats(msg, FakeServices())  # type: ignore[arg-type]
    assert "Воронка" in msg.replies[0]


async def test_cmd_costs_default_period() -> None:
    services = FakeServices()
    msg = FakeMessage("/costs")
    await cmd_costs(msg, services)  # type: ignore[arg-type]
    assert services.cost_days == [30]
    assert "$" in msg.replies[0]


async def test_cmd_costs_custom_period() -> None:
    services = FakeServices()
    msg = FakeMessage("/costs 7")
    await cmd_costs(msg, services)  # type: ignore[arg-type]
    assert services.cost_days == [7]


async def test_cmd_costs_bad_arg_falls_back() -> None:
    services = FakeServices()
    msg = FakeMessage("/costs abc")
    await cmd_costs(msg, services)  # type: ignore[arg-type]
    assert services.cost_days == [30]


async def test_review_empty_no_dialog() -> None:
    services = FakeServices()
    services.review_candidates = []
    state = FakeState()
    msg = FakeMessage("/review")
    await cmd_review(msg, services, state)  # type: ignore[arg-type]
    assert "нет" in msg.replies[0].lower()
    assert state.state is None  # диалог не начат


async def test_review_starts_and_sends_first_card() -> None:
    services = FakeServices()
    services.review_candidates = [_candidate("1", "relevant"), _candidate("2", "irrelevant")]
    state = FakeState()
    msg = FakeMessage("/review")
    await cmd_review(msg, services, state)  # type: ignore[arg-type]
    assert state.state == ReviewFlow.reviewing
    assert "EM 1" in msg.replies[0]
    assert msg.markups[0] is not None  # клавиатура 👍/👎


async def test_review_full_dialog_reports_agreement() -> None:
    services = FakeServices()
    services.review_candidates = [_candidate("1", "relevant"), _candidate("2", "irrelevant")]
    state = FakeState()
    await cmd_review(FakeMessage("/review"), services, state)  # type: ignore[arg-type]

    cb1 = FakeCallback("rev:up")  # владелец: relevant
    await on_review(cb1, services, state)  # type: ignore[arg-type]
    # первый обработан, второй показан
    assert any("EM 2" in r for r in cb1.message.replies)

    cb2 = FakeCallback("rev:down")  # владелец: irrelevant
    await on_review(cb2, services, state)  # type: ignore[arg-type]

    assert services.recorded == [("1", "relevant"), ("2", "irrelevant")]
    # финал — сводка agreement rate, состояние очищено
    assert any("%" in r for r in cb2.message.replies)
    assert state.state is None
