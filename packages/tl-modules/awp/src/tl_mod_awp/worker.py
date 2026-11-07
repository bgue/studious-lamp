"""The worker of the awp jobs: one kind, ``awp.rollup`` (spec m3-wbs-cwp section 4; ADR-0014).

``tl awp worker`` (T04) and the demos build their worker with ``build_worker``. The rollup is a
system job: ``prepare`` reads the typed tables of one project (no record text, no viewer filter),
``run`` is pure arithmetic (``rollup.compute``), ``settle`` appends ``WBSNode.BudgetRolledUp`` for
the nodes whose figures changed (at most 500, correlation ``rollup:<run id>``, source
``job:awp.rollup``) and queues the run again when more nodes remain or a request came in while it
ran (decision D-c). A job has no record, so ``started``, ``failed`` and ``expired`` write nothing;
the queue row keeps the error code.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, make_uow_factory
from tl_adapters.queue import job_queue_for
from tl_core.jobs import JobFailure, JobRunner
from tl_core.jobs.types import DEFAULT_LEASE_S, Claim, Clock, Expired, UowFactory
from tl_core.ledger import NewEvent
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_awp import rollup
from tl_mod_awp.common import silent, version_of
from tl_mod_awp.names import (
    CWP_ALLOCATION_TABLE,
    CWP_TABLE,
    JOB_KIND_ROLLUP,
    WBS_ALLOCATION_TABLE,
    WBS_NODE,
    WBS_NODE_TABLE,
)
from tl_mod_awp.readiness.follow import Follower
from tl_mod_awp.readiness.job import ReadinessKind

_HEAD_SQL = text("SELECT COALESCE(MAX(seq), 0) FROM events")
_NODES_SQL = text(f"SELECT id, parent_id FROM {WBS_NODE_TABLE} WHERE scope = :scope")
_MAPPING_SQL = text(
    f"SELECT node_id, cost_code_id, percent FROM {WBS_ALLOCATION_TABLE} WHERE scope = :scope"
)
# every state counts (it is budget); only a void CWP is out
_BUDGETS_SQL = text(
    f"SELECT c.id, c.budget_hours FROM {CWP_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.scope = :scope AND c.budget_hours IS NOT NULL AND r.voided = :voided"
)
_ALLOC_SQL = text(
    f"SELECT cwp_id, wbs_node_id, percent FROM {CWP_ALLOCATION_TABLE} WHERE scope = :scope"
)
_STORED_SQL = text(
    f"SELECT subject_id, line, cost_code_id, value FROM {rollup.ROLLUP_TABLE} "
    "WHERE scope = :scope AND subject_kind = :kind AND measure = :measure"
)
_SCOPES_SQL = text(f"SELECT DISTINCT scope FROM {WBS_NODE_TABLE}")
_LAST_RUN_SQL = text(
    f"SELECT COALESCE(MAX(as_of_seq), 0) FROM {rollup.ROLLUP_TABLE} WHERE scope = :scope"
)


@dataclass(frozen=True)
class Work:
    """What ``prepare`` read: plain data, so ``run`` needs no connection."""

    scope: str
    as_of_seq: int
    parents: dict[str, str | None]
    mapping: dict[str, list[tuple[str, Decimal]]]
    budgets: dict[str, Decimal]
    allocations: list[tuple[str, str, Decimal]]
    stored: dict[str, rollup.Figure]


@dataclass(frozen=True)
class Outcome:
    """The run: the nodes to write (at most 500), how many more wait, and the run id."""

    scope: str
    run_id: str
    as_of_seq: int
    changed: list[tuple[str, rollup.Figure]]
    remaining: int


def _stored(conn: Connection, scope: str) -> dict[str, rollup.Figure]:
    totals: dict[str, str] = {}
    lines: dict[str, list[tuple[rollup.Key, str]]] = {}
    params = {"scope": scope, "kind": rollup.SUBJECT_KIND, "measure": rollup.MEASURE}
    for r in conn.execute(_STORED_SQL, params):
        if r.line == rollup.LINE_TOTAL:
            totals[r.subject_id] = r.value
        else:
            lines.setdefault(r.subject_id, []).append((r.cost_code_id, r.value))
    return {
        node: rollup.Figure(
            total, tuple(sorted(lines.get(node, []), key=lambda e: rollup.line_order(e[0])))
        )
        for node, total in totals.items()
    }


class RollupKind:
    kind = JOB_KIND_ROLLUP

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        return None

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Work:
        conn = uow.conn()
        scope = claim.scope
        as_of = int(
            conn.execute(_HEAD_SQL).scalar_one()
        )  # read first: the data is at least this new
        params = {"scope": scope}
        parents = {str(r.id): r.parent_id for r in conn.execute(_NODES_SQL, params)}
        mapping: dict[str, list[tuple[str, Decimal]]] = {}
        for r in conn.execute(_MAPPING_SQL, params):
            mapping.setdefault(r.node_id, []).append((r.cost_code_id, Decimal(r.percent)))
        budgets = {
            str(r.id): Decimal(r.budget_hours)
            for r in conn.execute(_BUDGETS_SQL, {"scope": scope, "voided": False})
        }
        allocations = [
            (r.cwp_id, r.wbs_node_id, Decimal(r.percent)) for r in conn.execute(_ALLOC_SQL, params)
        ]
        return Work(scope, as_of, parents, mapping, budgets, allocations, _stored(conn, scope))

    def run(self, work: Work) -> Outcome:
        figures = rollup.compute(work.parents, work.mapping, work.budgets, work.allocations)
        changed: list[tuple[str, rollup.Figure]] = []
        for node in sorted(figures):  # ULIDs: the oldest nodes first; the order is fixed
            figure = figures[node]
            before = work.stored.get(node)
            if before is None and rollup.is_zero(figure):
                continue  # no row means no budget; nothing to say
            if before != figure:
                changed.append((node, figure))
        return Outcome(
            scope=work.scope,
            run_id=new_ulid(),
            as_of_seq=work.as_of_seq,
            changed=changed[: rollup.BATCH_NODES],
            remaining=max(0, len(changed) - rollup.BATCH_NODES),
        )

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Outcome) -> None:
        for node, figure in outcome.changed:
            payload = silent(
                {
                    "run_id": outcome.run_id,
                    "as_of_seq": outcome.as_of_seq,
                    "total": figure.total,
                    "by_cost_code": [
                        {"cost_code_id": code, "value": value} for code, value in figure.lines
                    ],
                }
            )
            uow.append(
                stream_id=node,
                stream_type=WBS_NODE,
                scope=outcome.scope,
                expected_version=version_of(uow, node),
                events=[NewEvent(event_type=rollup.BUDGET_ROLLED_UP, payload=payload)],
                actor=rollup.ACTOR,
                source=rollup.SOURCE,
                correlation_id=f"{rollup.CORRELATION_PREFIX}{outcome.run_id}",
                causation_id=None,
            )
        # the queue row is done in this transaction, so ``request`` can queue it again
        if outcome.remaining > 0:
            rollup.request(uow, outcome.scope)
        else:
            rollup.requeue_if_moved(uow, outcome.scope, outcome.as_of_seq)

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


class Worker:
    """A job runner and the engine it owns. Use as a context manager or call :meth:`close`."""

    def __init__(self, runner: JobRunner, open_uow: UowFactory) -> None:
        self.runner = runner
        self.follower = Follower(open_uow)
        self._open_uow = open_uow

    def close(self) -> None:
        dispose = getattr(self._open_uow, "dispose", None)
        if callable(dispose):
            dispose()

    def __enter__(self) -> Worker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def build_worker(
    target: DbTarget,
    *,
    worker_id: str | None = None,
    lease_s: float = DEFAULT_LEASE_S,
    clock: Clock = utcnow,
) -> Worker:
    """A worker that serves the ``awp.rollup`` and ``awp.readiness`` jobs at ``target``.

    ``worker.runner`` has ``run_once``, ``run_until_idle`` and ``serve``.
    """
    open_uow = make_uow_factory(target)
    with open_uow() as uow:
        queue = job_queue_for(uow.conn())
    runner = JobRunner(
        open_uow,
        queue,
        [RollupKind(), ReadinessKind()],
        worker_id=worker_id,
        lease_s=lease_s,
        clock=clock,
    )
    return Worker(runner, open_uow)


def requeue_orphans(target: DbTarget) -> int:
    """Queue the rollup of each project whose ledger moved past its last run and has no queued job
    (after a restore the queue is empty); the count queued. A project that never rolled up counts
    from the start of the ledger."""
    open_uow = make_uow_factory(target)
    queued = 0
    try:
        with open_uow() as uow:
            conn = uow.conn()
            for scope in [str(r.scope) for r in conn.execute(_SCOPES_SQL)]:
                last = int(conn.execute(_LAST_RUN_SQL, {"scope": scope}).scalar_one())
                if rollup.moved_since(conn, scope, last) and rollup.request(uow, scope):
                    queued += 1
        return queued
    finally:
        open_uow.dispose()
