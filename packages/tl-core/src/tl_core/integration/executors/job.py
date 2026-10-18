# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false
"""The ``job`` action executor: run a registered, pure ``ActionJob`` (brief §18.7; FANOUT D8).

STUB (P1-I7-T02a): ``failed``, ``use_jobs``, ``_factory``, ``has_job`` and the module state are
final; ``result_problem`` and ``JobExecutor.execute`` raise NotImplementedError. Remove this
paragraph, every STEPS comment, the two lint-silencing lines above and `NotImplementedError` when
you implement them.

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
    # STEPS
    # 1. No result (None): return None.
    # 2. Size = len of the UTF-8 bytes of `json.dumps(result, sort_keys=True,
    #    separators=(",", ":"))`. Catch TypeError, ValueError, OverflowError and RecursionError
    #    (an object, a cycle, a huge integer): return Problem(code="bad_outcome",
    #    message="The job's result is not JSON.").
    # 3. Size over ACTION_MAX_RESULT_BYTES: Problem(code="result_too_large",
    #    message=f"The job's result is over {ACTION_MAX_RESULT_BYTES} bytes."). A result of
    #    exactly that size is fine.
    # 4. Otherwise None.
    raise NotImplementedError


class JobExecutor:
    kind: ExecutorKind = "job"

    def execute(self, request: ActionRequest) -> ActionOutcome:
        # STEPS (every failure is `failed(code, message)`; nothing is raised)
        # 1. `request.config` is not a JobExecutorConfig: "wrong_executor",
        #    "This is not a job action."
        # 2. `factory = _factory(config.job)`. If that raises anything (Exception):
        #    "job_unavailable", f"The job could not be loaded ({type(exc).__name__})."
        #    A None factory: "unknown_job", f"No job is registered as {config.job}."
        # 3. `job = factory()`; if that raises: the same "job_unavailable" answer.
        # 4. `job` is not an ActionJob (isinstance with the runtime-checkable protocol) or its
        #    `.name` differs from `config.job`: "job_mismatch",
        #    f"The code registered as {config.job} is not that job."
        # 5. `outcome = job.run(request)`; any Exception: "job_error",
        #    f"The job failed ({type(exc).__name__})." Never put `str(exc)` in a message.
        # 6. `outcome` is not an ActionOutcome: "bad_outcome", "The job did not return an
        #    outcome." (pyright calls the isinstance redundant: silence it with the comment
        #    `# pyright: ignore[reportUnnecessaryIsInstance]`.)
        # 7. `problem = result_problem(outcome)`; if set, return ActionOutcome(status="failed",
        #    problems=[problem]).
        # 8. Return `outcome` unchanged (a failed outcome keeps its `retryable` flag).
        raise NotImplementedError
