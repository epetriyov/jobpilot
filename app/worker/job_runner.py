"""Раннер плановых задач: JobRun + root OTel span + structlog с trace_id ([F-I3], §5).

Каждый плановый job оборачивается: запись job_run, root-спан, и trace_id,
привязанный в structlog-контекст — так он попадает во ВСЕ логи прогона.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

import structlog
from opentelemetry import trace

from app.obs.tracing import current_trace_id
from app.ports.repositories import JobRunRepositoryPort

log = structlog.get_logger("worker.job_runner")
tracer = trace.get_tracer("jobpilot.worker")

# job(ctx) -> (items_in, items_out); ctx["partial"]=True переводит прогон в partial
JobFn = Callable[[dict[str, Any]], Awaitable[tuple[int, int]]]


class JobFailed(RuntimeError):
    """Обёртка над упавшим job — прогон зафиксирован как error, исключение проброшено."""


async def run_job(job_name: str, repo: JobRunRepositoryPort, job: JobFn) -> None:
    with tracer.start_as_current_span(f"job.{job_name}"):
        trace_id = current_trace_id()
        structlog.contextvars.bind_contextvars(trace_id=trace_id, job=job_name)
        try:
            run_id = await repo.start(job_name, trace_id)
            log.info("job_started")
            ctx: dict[str, Any] = {}
            try:
                items_in, items_out = await job(ctx)
            except Exception as exc:
                await repo.finish(run_id, status="error", error=repr(exc))
                log.error("job_failed", error=str(exc))
                raise JobFailed(job_name) from exc

            status: Literal["success", "partial"] = (
                "partial" if ctx.get("partial") else "success"
            )
            await repo.finish(run_id, status=status, items_in=items_in, items_out=items_out)
            log.info("job_finished", status=status, items_in=items_in, items_out=items_out)
        finally:
            structlog.contextvars.clear_contextvars()
