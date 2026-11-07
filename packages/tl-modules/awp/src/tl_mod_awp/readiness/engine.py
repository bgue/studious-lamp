"""Evaluate one IWP against every registered check and record the outcome (P2-I2 S4).

``evaluate`` reads (facts, then each check on the given connection); ``record`` writes in the
caller's unit of work: the check-sourced constraints, the Constraint check <-> Ready move, the
``IWP.ReadinessEvaluated`` event and ``IWP.Ready`` when it turns ready. The job (``job.py``)
splits the two across its read and write transactions; ``evaluate_now`` does both in one.

A check that raises, runs past ``CHECK_MAX_SECONDS`` or answers more than the contract allows is
``unknown`` with a fixed detail, never truncated. ``ready`` is true when every check is ``ok`` or
``n_a`` (README D9); ``unknown``, ``pending`` and ``blocked`` all make it false. ``resolve_via``
carries record ids only (the key slot repeats the id) and the engine adds no record text.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

from sqlalchemy import Connection, text
from tl_adapters.queue import job_queue_for
from tl_core import constraints
from tl_core.jobs import DEFAULT_MAX_ATTEMPTS
from tl_core.jobs.types import CANCELLED, DONE, FAILED, QUEUED, iso_z
from tl_core.ledger import NewEvent
from tl_core.readiness.registry import load_checks
from tl_core.readiness.types import (
    CHECK_MAX_SECONDS,
    MAX_DETAIL_CHARS,
    MAX_NAME_CHARS,
    MAX_RESOLVE_VIA,
    CheckResult,
    IwpFacts,
    ReadinessCheck,
)
from tl_core.services.commands import Command
from tl_core.services.errors import GuardFailedError
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_awp.common import append, move, record_state, setting_value, silent
from tl_mod_awp.facts import INITIAL_STATUS, iwp_facts
from tl_mod_awp.names import (
    CONSTRAINT_TABLE,
    IWP,
    IWP_CHECK,
    IWP_READINESS_EVALUATED,
    IWP_READY,
    IWP_READY_EVENT,
    JOB_KIND_READINESS,
    READINESS_ACTOR,
    READINESS_JOB_PREFIX,
    READINESS_SOURCE,
    READINESS_TABLE,
    TRANSITION_READY,
    TRANSITION_UNREADY,
)
from tl_mod_awp.readiness.checks import NAME as CONSTRAINTS_CLEARED
from tl_mod_awp.readiness.views import ReadinessView

Clock = Callable[[], float]
Checks = Mapping[str, ReadinessCheck]

#: At most this many raises and clears of check-sourced constraints in one run.
MAX_CONSTRAINT_CALLS: Final = 9
PASSING: Final = frozenset({"ok", "n_a"})
#: The category a check-sourced constraint carries; other names are ``other``.
CATEGORY: Final = {
    "materials_reserved": "materials",
    "documents_current": "engineering",
    "rfis_answered": "rfi",
}
DETAIL_RAISED: Final = "the check could not be run"
DETAIL_BOUND: Final = "the check ran past its time bound"
DETAIL_SHAPE: Final = "the check answered more than the contract allows"
RAISE_TEXT: Final = "readiness check {name} is blocked"
CLEAR_REASON: Final = "check passed"
READY_REASON: Final = "readiness evaluated ready"
UNREADY_REASON: Final = "readiness evaluated not ready"
_OPEN_SQL = text(
    f"SELECT c.id FROM {CONSTRAINT_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.subject_id = :iwp AND c.check_name = :name AND c.source = 'check' "
    "AND (r.status IS NULL OR r.status NOT IN ('Cleared', 'Withdrawn')) ORDER BY c.id LIMIT 1"
)
_SCOPE_SQL = text("SELECT scope FROM cur_core_record WHERE id = :id AND type = :type")
_REQUEUE_SQL = text(
    "UPDATE job_queue SET state = :queued, attempt = 0, run_after = :now, lease_owner = NULL, "
    "lease_until = NULL, started_at = NULL, finished_at = NULL, last_error = NULL, "
    "enqueued_at = :now WHERE job_id = :job_id AND state IN (:done, :failed, :cancelled)"
)
_EXISTS_SQL = text("SELECT 1 FROM cur_core_record WHERE id = :id")
_PREVIOUS_SQL = text(f"SELECT ready FROM {READINESS_TABLE} WHERE iwp_id = :id")


@dataclass(frozen=True)
class Evaluation:
    """What the checks said, before anything is written."""

    facts: IwpFacts
    today: date
    evaluated_at: str
    results: list[CheckResult]


def facts_hash(facts: IwpFacts) -> str:
    """SHA-256 hex of the canonical ``IwpFacts``."""
    canonical = json.dumps(facts.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def is_ready(results: list[CheckResult]) -> bool:
    """Every check is ``ok`` or ``n_a`` (D9); one ``unknown`` makes it false."""
    return all(r.state in PASSING for r in results)


def _unknown(check: ReadinessCheck, detail: str) -> CheckResult:
    return CheckResult(
        name=str(check.name)[:MAX_NAME_CHARS],
        version=str(check.version),
        state="unknown",
        detail=detail,
    )


def _within_contract(check: ReadinessCheck, result: object) -> CheckResult | None:
    """``result`` with its record ids as keys, or ``None`` when it breaks the contract."""
    if not isinstance(result, CheckResult):
        return None
    if result.name != check.name or result.version != check.version:
        return None
    if len(result.resolve_via) > MAX_RESOLVE_VIA or len(result.detail) > MAX_DETAIL_CHARS:
        return None
    refs = [r.model_copy(update={"key": r.record_id}) for r in result.resolve_via]
    return result.model_copy(update={"resolve_via": refs})


def run_check(
    check: ReadinessCheck, conn: Connection, facts: IwpFacts, today: date, clock: Clock
) -> CheckResult:
    """One check, bounded: any failure is ``unknown`` with a fixed detail."""
    started = clock()
    try:
        with conn.begin_nested():
            answer = check.evaluate(conn, facts, today)
    except Exception:  # noqa: BLE001 - a check that raises is unknown, whatever it raised
        return _unknown(check, DETAIL_RAISED)
    if clock() - started > CHECK_MAX_SECONDS:
        return _unknown(check, DETAIL_BOUND)
    kept = _within_contract(check, answer)
    return _unknown(check, DETAIL_SHAPE) if kept is None else _drop_missing(conn, kept)


def _drop_missing(conn: Connection, result: CheckResult) -> CheckResult:
    """Fail closed: a ``resolve_via`` id that is no record is dropped and counted in the detail."""
    found = [
        r
        for r in result.resolve_via
        if conn.execute(_EXISTS_SQL, {"id": r.record_id}).first() is not None
    ]
    gone = len(result.resolve_via) - len(found)
    if not gone:
        return result
    note = f"{gone} reference{'s' if gone > 1 else ''} not found"
    detail = f"{result.detail}; {note}" if result.detail else note
    if len(detail) > MAX_DETAIL_CHARS:
        detail = note
    return result.model_copy(update={"resolve_via": found, "detail": detail})


def evaluate(
    conn: Connection,
    iwp_id: str,
    today: date,
    checks: Checks | None = None,
    *,
    clock: Clock = time.monotonic,
    now: datetime | None = None,
) -> Evaluation:
    """Read the facts of the IWP and run every check (sorted by name). ``LookupError``: no IWP."""
    found = load_checks() if checks is None else checks
    facts = iwp_facts(conn, iwp_id)
    results = [run_check(found[name], conn, facts, today, clock) for name in sorted(found)]
    return Evaluation(facts, today, iso_z(now or utcnow()), results)


def _open_check_constraint(conn: Connection, iwp_id: str, name: str) -> str | None:
    found = conn.execute(_OPEN_SQL, {"iwp": iwp_id, "name": name}).scalar_one_or_none()
    return None if found is None else str(found)


def _due_at(conn: Connection, facts: IwpFacts) -> str | None:
    """Planned start minus ``awp.iwp.ready_lead_weeks`` weeks (ISO date); none without a start."""
    if facts.planned_start is None:
        return None
    weeks = int(setting_value(conn, facts.scope, "awp.iwp.ready_lead_weeks") or 0)
    return (facts.planned_start - timedelta(weeks=weeks)).isoformat()


def sync_constraints(uow: UnitOfWork, facts: IwpFacts, results: list[CheckResult]) -> bool:
    """Raise one constraint per blocked check, clear the open one of a check that passes.

    ``constraints_cleared`` is skipped (it reads constraints, it does not raise them). At most
    ``MAX_CONSTRAINT_CALLS`` calls; ``suppressed`` and ``exists`` are recorded nowhere. ``True``
    when a constraint was raised or cleared.
    """
    conn = uow.conn()
    calls = 0
    changed = False
    for result in results:
        if result.name == CONSTRAINTS_CLEARED or calls >= MAX_CONSTRAINT_CALLS:
            continue
        if result.state == "blocked":
            calls += 1
            digest = hashlib.sha256(
                f"{result.name}\n{result.state}\n{result.detail}".encode()
            ).hexdigest()
            due = _due_at(conn, facts)
            extra = {} if due is None else {"due_at": due}
            outcome = constraints.raise_constraint(
                uow,
                subject_id=facts.record_id,
                phase="ready",
                severity="blocking",
                category=CATEGORY.get(result.name, "other"),
                source="check",
                check_name=result.name,
                facts_hash=digest,
                by_module="awp",
                description=RAISE_TEXT.format(name=result.name),
                **extra,
            )
            changed = changed or outcome.action == "raised"
        elif result.state in PASSING:
            open_id = _open_check_constraint(conn, facts.record_id, result.name)
            if open_id is None:
                continue
            calls += 1
            outcome = constraints.clear_constraint(
                uow, constraint_id=open_id, reason=CLEAR_REASON, by_module="awp"
            )
            changed = changed or outcome.action == "cleared"
    return changed


def _replace(results: list[CheckResult], new: CheckResult) -> list[CheckResult]:
    swapped = [new if r.name == new.name else r for r in results]
    return swapped if any(r.name == new.name for r in results) else [*swapped, new]


def record(
    uow: UnitOfWork,
    evaluation: Evaluation,
    checks: Checks | None = None,
    *,
    clock: Clock = time.monotonic,
) -> ReadinessView:
    """Write ``evaluation``: constraints, the move, ``IWP.ReadinessEvaluated``, ``IWP.Ready``."""
    conn = uow.conn()
    facts = evaluation.facts
    iwp = facts.record_id
    found = load_checks() if checks is None else checks
    results = list(evaluation.results)
    if sync_constraints(uow, facts, results) and CONSTRAINTS_CLEARED in found:
        # the constraints this run raised or cleared change what that check counts
        again = run_check(found[CONSTRAINTS_CLEARED], conn, facts, evaluation.today, clock)
        results = _replace(results, again)
    ready = is_ready(results)
    cmd = Command(
        actor=READINESS_ACTOR,
        source=READINESS_SOURCE,
        scope=facts.scope,
        correlation_id=new_ulid(),
    )
    state = record_state(conn, iwp, INITIAL_STATUS)
    if ready and state == IWP_CHECK:
        try:
            with conn.begin_nested():
                move(uow, cmd, iwp, TRANSITION_READY, READY_REASON)
        except GuardFailedError as refusal:  # the refusal is the outcome
            blocked = CheckResult(
                name=CONSTRAINTS_CLEARED,
                version="1",
                state="blocked",
                detail=str(refusal)[:MAX_DETAIL_CHARS],
            )
            results = _replace(results, blocked)
            ready = False
    elif not ready and state == IWP_READY:
        move(uow, cmd, iwp, TRANSITION_UNREADY, UNREADY_REASON)
    # IWP.Ready only for an IWP that is Ready after this run (not Draft, Issued, ...)
    now_ready = ready and record_state(conn, iwp, INITIAL_STATUS) == IWP_READY
    before = conn.execute(_PREVIOUS_SQL, {"id": iwp}).scalar_one_or_none()
    view = ReadinessView(
        iwp_id=iwp,
        evaluated_at=evaluation.evaluated_at,
        today=evaluation.today.isoformat(),
        ready=ready,
        facts_hash=facts_hash(facts),
        checks=results,
    )
    events = [
        NewEvent(
            event_type=IWP_READINESS_EVALUATED,
            payload=silent(
                {
                    "iwp_id": iwp,
                    "evaluated_at": view.evaluated_at,
                    "today": view.today,
                    "ready": ready,
                    "checks": [r.model_dump(mode="json") for r in results],
                    "facts_hash": view.facts_hash,
                }
            ),
        )
    ]
    if now_ready and not before:
        events.append(
            NewEvent(
                event_type=IWP_READY_EVENT,
                payload={"iwp_id": iwp, "evaluated_at": view.evaluated_at},
            )
        )
    append(uow, cmd, iwp, IWP, events)
    return view


def evaluate_now(
    uow: UnitOfWork,
    iwp_id: str,
    today: date,
    checks: Checks | None = None,
    *,
    clock: Clock = time.monotonic,
) -> ReadinessView:
    """The same evaluation inside the caller's request; it appends the same event."""
    found = load_checks() if checks is None else checks
    evaluation = evaluate(uow.conn(), iwp_id, today, found, clock=clock)
    return record(uow, evaluation, found, clock=clock)


def request(uow: UnitOfWork, iwp_ids: Sequence[str], *, reason: str) -> int:
    """Queue one ``awp.readiness`` job per IWP not already queued (job id ``ready:<iwp id>``).

    Returns how many were queued. An id that is no IWP is skipped; a repeated id counts once; a
    job that finished is queued again. ``reason`` is for the caller's log (the queue keeps none).
    """
    conn = uow.conn()
    queue = job_queue_for(conn)
    now = utcnow()
    queued = 0
    for iwp_id in dict.fromkeys(iwp_ids):
        scope = conn.execute(_SCOPE_SQL, {"id": iwp_id, "type": IWP}).scalar_one_or_none()
        if scope is None:
            continue
        made = f"{READINESS_JOB_PREFIX}{iwp_id}"
        found = queue.get(conn, made)
        if found is None:
            queue.enqueue(
                conn,
                job_id=made,
                kind=JOB_KIND_READINESS,
                scope=str(scope),
                now=now,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
            )
            queued += 1
        elif found.state != QUEUED:
            params = {
                "queued": QUEUED,
                "done": DONE,
                "failed": FAILED,
                "cancelled": CANCELLED,
                "now": iso_z(now),
                "job_id": made,
            }
            queued += conn.execute(_REQUEUE_SQL, params).rowcount
    return queued


def now_date() -> date:
    return utcnow().astimezone(UTC).date()
