"""The ``job`` action executor: run a registered, pure ``ActionJob`` (brief §18.7; FANOUT D8).

A ``job`` action names a job (``JobExecutorConfig.job``). The code that job runs is found only
through the entry-point group ``throughline.action_jobs`` (``ACTION_JOB_ENTRY_POINT``): an admin
chooses among installed jobs, never supplies code. A job is pure (no ledger, no unit of work, no
network, no secret); its result is stored on the invocation.

The executor never raises for a bad request or a bad answer. Whatever the job does wrong (it
raises, it returns the wrong thing, its result is not JSON or is too large) is a ``failed``
outcome with a fixed code. The text of an exception is never copied into a message: it may hold a
path or a value from the request, so only the exception *type* is named.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from importlib.metadata import entry_points
from typing import Any

from tl_core.integration.contract import (
    ACTION_JOB_ENTRY_POINT,
    ACTION_MAX_RESULT_BYTES,
    ActionJob,
    ActionOutcome,
    ActionRequest,
    ExecutorKind,
    JobExecutorConfig,
    Problem,
)

#: A factory of jobs by name: an entry point's class, or a test's own.
JobFactory = Callable[[], Any]

_overrides: Mapping[str, JobFactory] | None = None


def failed(code: str, message: str) -> ActionOutcome:
    """A ``failed`` outcome that will not be retried."""
    return ActionOutcome(status="failed", problems=[Problem(code=code, message=message)])


@contextmanager
def use_jobs(jobs: Mapping[str, JobFactory]) -> Generator[None]:
    """Use exactly these jobs (by name) instead of the entry points, for a test."""
    global _overrides
    before = _overrides
    _overrides = jobs
    try:
        yield
    finally:
        _overrides = before


def _factory(name: str) -> JobFactory | None:
    """The factory registered under ``name``; raises what loading an entry point raises."""
    if _overrides is not None:
        return _overrides.get(name)
    for point in entry_points(group=ACTION_JOB_ENTRY_POINT):
        if point.name == name:
            return point.load()
    return None


def has_job(name: str) -> bool:
    """Whether a job is registered as ``name`` (a job that cannot be loaded counts as absent)."""
    try:
        return _factory(name) is not None
    except Exception:
        return False


def result_problem(outcome: ActionOutcome) -> Problem | None:
    """Why ``outcome.result`` cannot be stored: not JSON, or over ``ACTION_MAX_RESULT_BYTES``."""
    if outcome.result is None:
        return None
    try:
        text = json.dumps(outcome.result, sort_keys=True, separators=(",", ":"))
        size = len(text.encode("utf-8"))
    except (TypeError, ValueError, OverflowError, RecursionError):
        return Problem(code="bad_outcome", message="The job's result is not JSON.")
    if size > ACTION_MAX_RESULT_BYTES:
        return Problem(
            code="result_too_large",
            message=f"The job's result is over {ACTION_MAX_RESULT_BYTES} bytes.",
        )
    return None


def _unavailable(exc: Exception) -> ActionOutcome:
    """The ``job_unavailable`` answer: only the exception's type is named."""
    return failed("job_unavailable", f"The job could not be loaded ({type(exc).__name__}).")


class JobExecutor:
    kind: ExecutorKind = "job"

    def execute(self, request: ActionRequest) -> ActionOutcome:
        config = request.config
        if not isinstance(config, JobExecutorConfig):
            return failed("wrong_executor", "This is not a job action.")
        try:
            factory = _factory(config.job)
        except Exception as exc:
            return _unavailable(exc)
        if factory is None:
            return failed("unknown_job", f"No job is registered as {config.job}.")
        try:
            job = factory()
        except Exception as exc:
            return _unavailable(exc)
        if not isinstance(job, ActionJob) or job.name != config.job:
            return failed("job_mismatch", f"The code registered as {config.job} is not that job.")
        try:
            outcome = job.run(request)
        except Exception as exc:
            return failed("job_error", f"The job failed ({type(exc).__name__}).")
        if not isinstance(outcome, ActionOutcome):  # pyright: ignore[reportUnnecessaryIsInstance]
            return failed("bad_outcome", "The job did not return an outcome.")
        problem = result_problem(outcome)
        if problem is not None:
            return ActionOutcome(status="failed", problems=[problem])
        return outcome
