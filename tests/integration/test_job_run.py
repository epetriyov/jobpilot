"""[F-I3] Упавший job → job_run.status=error, error заполнен, trace_id во всех логах прогона."""

import io

import pytest
import structlog

from app.obs.logging import configure_logging
from app.obs.tracing import setup_tracing
from app.worker.job_runner import JobFailed, run_job


class InMemoryJobRunRepo:
    def __init__(self) -> None:
        self.rows: dict[int, dict] = {}
        self._next = 1

    async def start(self, job_name: str, trace_id: str) -> int:
        run_id = self._next
        self._next += 1
        self.rows[run_id] = {
            "job_name": job_name,
            "status": "running",
            "trace_id": trace_id,
            "error": None,
            "items_in": 0,
            "items_out": 0,
        }
        return run_id

    async def finish(self, run_id, *, status, items_in=0, items_out=0, error=None) -> None:
        self.rows[run_id].update(status=status, items_in=items_in, items_out=items_out, error=error)


@pytest.fixture(autouse=True)
def _tracing() -> None:
    setup_tracing(service_name="test-worker")


@pytest.fixture()
def log_output() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(secret_values=[], stream=stream)
    yield stream
    structlog.reset_defaults()


async def test_successful_job_records_success() -> None:
    repo = InMemoryJobRunRepo()

    async def work() -> tuple[int, int]:
        return 5, 3

    async def job(ctx: dict) -> tuple[int, int]:
        return await work()

    await run_job("smoke", repo, job)

    row = repo.rows[1]
    assert row["status"] == "success"
    assert row["items_in"] == 5 and row["items_out"] == 3
    assert row["error"] is None
    assert row["trace_id"]


async def test_failed_job_records_error_with_trace(log_output: io.StringIO) -> None:
    repo = InMemoryJobRunRepo()

    async def job(ctx: dict) -> tuple[int, int]:
        raise RuntimeError("scrape exploded")

    with pytest.raises(JobFailed):
        await run_job("smoke", repo, job)

    row = repo.rows[1]
    assert row["status"] == "error"
    assert "scrape exploded" in row["error"]
    assert row["trace_id"]

    # trace_id присутствует во всех логах прогона
    log_lines = [ln for ln in log_output.getvalue().splitlines() if ln.strip()]
    assert log_lines
    assert all(row["trace_id"] in ln for ln in log_lines)


async def test_partial_status_when_reported() -> None:
    repo = InMemoryJobRunRepo()

    async def job(ctx: dict) -> tuple[int, int]:
        ctx["partial"] = True
        return 2, 2

    await run_job("smoke", repo, job)
    assert repo.rows[1]["status"] == "partial"
