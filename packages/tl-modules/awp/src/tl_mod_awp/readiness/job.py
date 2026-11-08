"""The readiness job: kind ``awp.readiness``, one IWP per run, job id ``ready:<iwp id>``.

``prepare`` reads the facts and calls each check on the read connection; ``run`` passes the
evaluation on; ``settle`` writes it (``engine.record``). A job has no record of its own, so
``started``, ``failed`` and ``expired`` write nothing: the queue row keeps the error code.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from typing import Final

from tl_core.jobs import JobFailure
from tl_core.jobs.types import Claim, Expired
from tl_core.readiness.registry import load_checks
from tl_core.uow import UnitOfWork

from tl_mod_awp.names import JOB_KIND_READINESS, READINESS_JOB_PREFIX
from tl_mod_awp.readiness import engine

LEASE_S: Final = 60.0
NOT_FOUND: Final = "iwp not found"


def job_id(iwp_id: str) -> str:
    return f"{READINESS_JOB_PREFIX}{iwp_id}"


class ReadinessKind:
    kind = JOB_KIND_READINESS

    def __init__(
        self,
        checks: Callable[[], engine.Checks] = load_checks,
        today: Callable[[], date] = engine.now_date,
        clock: engine.Clock = time.monotonic,
    ) -> None:
        self._checks = checks
        self._today = today
        self._clock = clock

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        return None

    def prepare(self, uow: UnitOfWork, claim: Claim) -> engine.Evaluation:
        iwp_id = claim.job_id.removeprefix(READINESS_JOB_PREFIX)
        try:
            return engine.evaluate(
                uow.conn(), iwp_id, self._today(), self._checks(), clock=self._clock
            )
        except LookupError:
            raise JobFailure("not_found", NOT_FOUND, retryable=False) from None

    def run(self, work: engine.Evaluation) -> engine.Evaluation:
        return work

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: engine.Evaluation) -> None:
        engine.record(uow, outcome, self._checks(), clock=self._clock)

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        return None

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        return None
