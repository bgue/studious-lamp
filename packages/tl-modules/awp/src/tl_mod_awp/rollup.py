"""Request and compute the budget rollup (spec m3-wbs-cwp section 4; contracts section 7).

``request`` only queues: job id ``rollup:<scope>``, kind ``awp.rollup``. Every handler that changes
an allocation or retires a node or area calls it in its own unit of work, so the queue row and the
ledger events are one transaction. The run is ``worker.RollupKind``; the arithmetic is ``compute``
here (pure: exact ``Decimal``, no connection).

One row per scope: the job id is the primary key. A row that is ``queued`` already asks for a
run, so a second request changes nothing. A row that finished (``done``, ``failed``,
``cancelled``) is put back in the queue. A row that is ``running`` is left alone: the run read
the ledger when it started, so at settle it calls ``requeue_if_moved`` (decision D-c): when an
event that changes a figure came after the run's ``as_of_seq`` it queues itself again, once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from typing import Final

from sqlalchemy import Connection, text
from tl_adapters.queue import job_queue_for
from tl_core.jobs import DEFAULT_MAX_ATTEMPTS, iso_z
from tl_core.jobs.types import CANCELLED, DONE, FAILED, QUEUED
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_awp.names import JOB_KIND_ROLLUP, ROLLUP_JOB_PREFIX

ROLLUP_TABLE: Final = "cur_awp_rollup"
BUDGET_ROLLED_UP: Final = "WBSNode.BudgetRolledUp"
MEASURE: Final = "budget_hours"
SUBJECT_KIND: Final = "wbs_node"
LINE_TOTAL: Final = "total"
LINE_COST_CODE: Final = "cost_code"
LINE_UNALLOCATED: Final = "unallocated"
#: At most this many nodes get an event in one run; the settle queues the rest.
BATCH_NODES: Final = 500
ACTOR: Final = "svc:awp.rollup"
SOURCE: Final = f"job:{JOB_KIND_ROLLUP}"
CORRELATION_PREFIX: Final = "rollup:"

#: Events after a run's ``as_of_seq`` that change a figure (budget, allocation, move, retirement).
_FIGURE_EVENTS: Final = (
    "WBSNode.Revised",
    "WBSNode.Retired",
    "WBSNode.Reinstated",
    "WBSNode.CostCodesMapped",
    "CWP.Revised",
    "CWP.AllocatedToWbs",
)
_CWP_STREAM: Final = "awp.CWP"
_MOVED_SQL = text(
    "SELECT 1 FROM events WHERE scope = :scope AND seq > :as_of AND ("
    + "event_type IN ("
    + ", ".join(f":t{i}" for i in range(len(_FIGURE_EVENTS)))
    + ") OR (event_type = 'Record.Voided' AND stream_type = :cwp)) LIMIT 1"
)

_REQUEUE_SQL = text(
    "UPDATE job_queue SET state = :queued, attempt = 0, run_after = :now, lease_owner = NULL, "
    "lease_until = NULL, started_at = NULL, finished_at = NULL, last_error = NULL, "
    "enqueued_at = :now WHERE job_id = :job_id AND state IN (:done, :failed, :cancelled)"
)


def job_id(scope: str) -> str:
    return f"{ROLLUP_JOB_PREFIX}{scope}"


def request(uow: UnitOfWork, scope: str) -> bool:
    """Queue the rollup of ``scope`` unless one is queued. ``True`` when this call queued it."""
    conn = uow.conn()
    queue = job_queue_for(conn)
    made = job_id(scope)
    now = utcnow()
    found = queue.get(conn, made)
    if found is None:
        queue.enqueue(
            conn,
            job_id=made,
            kind=JOB_KIND_ROLLUP,
            scope=scope,
            now=now,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
        )
        return True
    if found.state == QUEUED:
        return False
    return (
        conn.execute(
            _REQUEUE_SQL,
            {
                "queued": QUEUED,
                "done": DONE,
                "failed": FAILED,
                "cancelled": CANCELLED,
                "now": iso_z(now),
                "job_id": made,
            },
        ).rowcount
        == 1
    )


def moved_since(conn: Connection, scope: str, as_of_seq: int) -> bool:
    """``True`` when an event that changes a figure of ``scope`` came after ``as_of_seq``."""
    params: dict[str, object] = {"scope": scope, "as_of": as_of_seq, "cwp": _CWP_STREAM}
    params.update({f"t{i}": name for i, name in enumerate(_FIGURE_EVENTS)})
    return conn.execute(_MOVED_SQL, params).first() is not None


def requeue_if_moved(uow: UnitOfWork, scope: str, as_of_seq: int) -> bool:
    """D-c: queue the run again when a request came in while it ran. Call at settle, after the
    queue row is ``done`` (so ``request`` can queue it). Two requests queue one run."""
    if not moved_since(uow.conn(), scope, as_of_seq):
        return False
    return request(uow, scope)


# --- the arithmetic ---------------------------------------------------------------------------

TENTH = Decimal("0.1")
_HUNDRED = Decimal(100)
Key = str | None  # a cost code id; ``None`` is the unallocated line


@dataclass(frozen=True)
class Figure:
    """The rounded figures of one node: ``total`` and ``lines`` (cost code id or ``None``, value),
    cost codes by id and the unallocated line last. The line values sum to ``total``."""

    total: str
    lines: tuple[tuple[Key, str], ...]


def line_order(key: Key) -> tuple[bool, str]:
    return (key is None, key or "")


def _tenths(value: Decimal) -> str:
    return format(value.quantize(TENTH), "f")


def split(parts: Mapping[Key, Decimal]) -> Figure:
    """Round exact ``parts`` to 0.1 h so they sum to the rounded total (largest remainder).

    The total is the exact sum rounded half to even; each part is cut down to a tenth and the
    tenths still missing go one each to the parts with the largest cut-off remainder (ties: the
    earlier line in order), so no figure drifts from the total.
    """
    keys = sorted(parts, key=line_order)
    total = sum(parts.values(), Decimal(0)).quantize(TENTH, rounding=ROUND_HALF_EVEN)
    floors = {k: (parts[k] * 10).to_integral_value(rounding=ROUND_FLOOR) for k in keys}
    missing = int(total * 10 - sum(floors.values()))
    by_remainder = sorted(keys, key=lambda k: (-(parts[k] * 10 - floors[k]), line_order(k)))
    for i in range(missing):
        floors[by_remainder[i % len(by_remainder)]] += 1
    return Figure(_tenths(total), tuple((k, _tenths(floors[k] / 10)) for k in keys))


def compute(
    parents: Mapping[str, str | None],
    mapping: Mapping[str, Sequence[tuple[str, Decimal]]],
    budgets: Mapping[str, Decimal],
    allocations: Sequence[tuple[str, str, Decimal]],
) -> dict[str, Figure]:
    """Figures of every node. ``parents`` maps node id to parent id; ``mapping`` maps a leaf to its
    ``(cost code id, percent)`` lines; ``budgets`` maps a non-void CWP to its hours; ``allocations``
    are ``(cwp id, node id, percent)``. Only leaves take CWP hours; a parent sums its children
    exactly and rounds once."""
    children: dict[str, list[str]] = {n: [] for n in parents}
    roots: list[str] = []
    for node, parent in parents.items():
        if parent is None or parent not in parents:
            roots.append(node)
        else:
            children[parent].append(node)
    hours: dict[str, Decimal] = {}
    for cwp, node, percent in allocations:
        if cwp in budgets and node in parents and not children[node]:
            hours[node] = hours.get(node, Decimal(0)) + budgets[cwp] * percent / _HUNDRED
    exact: dict[str, dict[Key, Decimal]] = {}
    order: list[str] = []
    stack = sorted(roots)
    while stack:
        node = stack.pop()
        order.append(node)
        stack.extend(children[node])
    for node in reversed(order):  # children before parents
        parts: dict[Key, Decimal] = {}
        if children[node]:
            for child in children[node]:
                for key, value in exact[child].items():
                    parts[key] = parts.get(key, Decimal(0)) + value
        else:
            base = hours.get(node, Decimal(0))
            lines = mapping.get(node, ())
            if lines:
                for code, percent in lines:
                    parts[code] = parts.get(code, Decimal(0)) + base * percent / _HUNDRED
            else:
                parts[None] = base
        exact[node] = parts
    return {node: split(parts) for node, parts in exact.items()}


def is_zero(figure: Figure) -> bool:
    return figure.total == "0.0" and all(value == "0.0" for _, value in figure.lines)
