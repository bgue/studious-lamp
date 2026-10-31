"""Readiness contracts for Phase 2 (brief §9 M3 "Readiness check"; 08-phase2-plan.md I2).

Frozen for the phase: change only by orchestrator decision.

A *readiness check* answers one question about one IWP from the live linked records ("documents
current", "materials reserved", "scaffold erected and tagged", ...). Checks are plugins found
through the entry-point group READINESS_ENTRY_POINT; each entry point names a zero-argument
callable that returns an object satisfying ReadinessCheck. The awp module runs them in a job
(kind JOB_KIND, one IWP per run) and appends one IWP.ReadinessEvaluated event with every result;
cur_awp_readiness is projected from that event, so a rebuild never calls a check.

A check is read-only: it gets a connection, never a unit of work, never writes, never raises for
a bad record (it answers "unknown" with a fixed detail), never opens the network, and keeps every
list it returns inside the bounds below. The module that ships a check owns the tables it reads;
the awp module never imports that module (the ADR-0010 and P1-I3 pattern).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from sqlalchemy import Connection

READINESS_ENTRY_POINT = "throughline.readiness_checks"
JOB_KIND = "awp.readiness"

#: Bounds on what one check may return (the parent refuses a result past any of them; the IWP's
#: evaluation is then "unknown" for that check, never truncated, as P1-I3 D10 did for results).
MAX_CHECKS = 32
MAX_RESOLVE_VIA = 50
MAX_DETAIL_CHARS = 500
MAX_NAME_CHARS = 64
#: Bounds on an evaluation run (the job claims one IWP; a check that takes longer fails the run
#: with a fixed code and the IWP keeps its previous evaluation).
CHECK_MAX_SECONDS = 10
EVALUATION_LEASE_S = 60.0

#: ok: nothing blocks this aspect. blocked: at least one resolve_via record must change.
#: pending: something was asked for and is not yet answered (a reservation requested, an RFI
#: open). n_a: the check's module or record type does not exist yet; detail names the decision.
#: unknown: the check could not answer (a bound was hit, a read failed); never blocks release
#: silently: the release command refuses an IWP with an unknown check unless the setting
#: awp.release.allow_unknown_checks is true.
CheckState = Literal["ok", "blocked", "pending", "n_a", "unknown"]


class IwpFacts(BaseModel):
    """What every check is told about the IWP. Read once per evaluation by the awp module
    (tl_mod_awp.facts.iwp_facts); checks read linked records themselves through the connection."""

    record_id: str
    scope: str  # the project scope
    key: str  # P123-IWP-PIP-0042
    status: str  # the workflow state, "Draft" when the record never moved (L-P1-I2-3)
    discipline: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    foreman: str | None = None  # an account actor string, user:<name>
    estimated_hours: float | None = None
    #: The ids of the records the IWP `contains`, by record type (scope items, tags; Phase 3 welds).
    scope_ids: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    #: Active links from the IWP that pin a document revision (relation references, pin set).
    pinned_document_links: list[str] = Field(default_factory=list[str])


class RecordRef(BaseModel):
    """A record a person can open to resolve a blocked check."""

    record_id: str
    record_type: str
    key: str


class CheckResult(BaseModel):
    name: str = Field(max_length=MAX_NAME_CHARS)
    version: str
    state: CheckState
    #: Fixed text plus the caller's keys and counts; no paths, no exception text.
    detail: str = Field(max_length=MAX_DETAIL_CHARS)
    #: Records whose change would move the state (a stale pin, an open constraint, a receipt).
    resolve_via: list[RecordRef] = Field(
        default_factory=list[RecordRef], max_length=MAX_RESOLVE_VIA
    )
    #: Counts for the screen ("5/7 drawings current"); None when the check has no denominator.
    count_ok: int | None = None
    count_total: int | None = None


@runtime_checkable
class ReadinessCheck(Protocol):
    """A plugin that answers one question about one IWP. Pure reads, no writes, no network."""

    #: Unique, snake case: "documents_current", "materials_reserved", "scaffold_tagged".
    name: str
    #: Bump when the answer for the same state changes.
    version: str
    #: Record types whose events ask for a re-evaluation of the IWPs that link them (the awp
    #: module subscribes to these; a check that reads tables no event names declares the type
    #: whose module writes those tables).
    watches: frozenset[str]

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP as of ``today`` (the job's clock; a simulation sets it)."""
        ...


# Event (schema/modules/awp/readiness_events.yaml, tl:event_type IWP.ReadinessEvaluated, stream
# of the IWP): {iwp_id, evaluated_at, today, ready: bool, checks: list[CheckResult] (bounded),
# facts_hash: sha256 of the canonical IwpFacts}. IWP.Ready (the brief's default webhook) is
# appended by the same job when `ready` turns true and the previous evaluation was not ready.
#
# Pipeline-side signatures, implemented in I2 WS-B and listed here so WS-A, I3 and I4 can test
# against them:
#   tl_core.readiness.registry.load_checks() -> dict[str, ReadinessCheck]
#       Loads READINESS_ENTRY_POINT. A plugin that fails to load is an error at first use, never a
#       silent gap (ADR-0010 decision 3). Two checks with one name is an error.
#   tl_mod_awp.readiness.request(uow, iwp_ids: Sequence[str], *, reason: str) -> int
#       Queues one JOB_KIND job per IWP not already queued (job id "ready:<iwp id>"); returns
#       how many were queued. Called by WS-A's commands (scope, pin, constraint changes) and by
#       the modules that ship checks when their state changes (a reservation, a tag colour).
#   tl_mod_awp.readiness.evaluate_now(uow, iwp_id, today) -> ReadinessView
#       The same evaluation inside a request, for the release command and the demo; bounded by
#       the same constants; it appends the same event.
#   tl_mod_awp.readiness.views.readiness(conn, scope, iwp_key) -> ReadinessView
#       From cur_awp_readiness (projected): the last evaluation, its checks, ready, evaluated_at.
# Every check ships with a test that calls
#   tests/contract/test_readiness_contract.py::check_readiness_contract(check, world)
# which proves: no write (a read-only connection; L-P1-I0B-4), bounds, fixed detail, n_a for a
# missing dependency, and that `watches` names existing record types.
