"""What other modules read from requisitions (contract section 3): the open requisitions that serve
a record, and the work order of a requisition.

Imports only ``tl_core`` and this module's own names. Every function takes ``viewer=`` and its
default is the lowest clearance (``confidentiality.LOWEST``), never the ambient viewer: a caller
that reads for a person says so. A requisition whose subject (``for_record_id``) the viewer may not
read is hidden whole, with its work order (``tl_core.confidentiality``, ``SUBJECT_LINKS``): it is
absent from the answers as a missing one is. Answers hold at most ``MAX_ROWS`` rows; more is a
``ValueError`` with a fixed message.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_requisitions.names import (
    KINDS,
    REQUISITION_FINAL,
    ST_OPEN,
    ST_REQUESTED,
    TABLES,
    WORK_ORDER_TABLE,
)

MAX_ROWS: Final = 500
MSG_TOO_MANY: Final = "more than 500 requisitions: narrow the question"


@dataclass(frozen=True)
class RequisitionRow:
    """A requisition as a reader sees it (the columns every kind has)."""

    id: str
    key: str
    kind: str
    record_type: str
    subject: str
    state: str
    requester: str
    priority: str
    need_by: str | None
    for_record_id: str | None
    approved_by: str | None
    work_order_id: str | None
    version: int


@dataclass(frozen=True)
class WorkOrderRow:
    id: str
    key: str
    requisition_id: str
    work_kind: str
    state: str
    assigned_to: str | None
    planned_start: str | None
    planned_finish: str | None
    actual_start: str | None
    actual_finish: str | None
    hours_planned: str | None
    hours_actual: str | None
    version: int


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


_FINAL = ", ".join(f"'{s}'" for s in sorted(REQUISITION_FINAL))


def open_requisitions_for(
    conn: Connection,
    record_id: str,
    *,
    kinds: Collection[str] | None = None,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[RequisitionRow]:
    """The requisitions that serve ``record_id`` (an IWP or CWP) and are not final (Closed,
    Rejected, Cancelled), by key. ``kinds`` limits them (``labor``, ``material``, ``general``,
    ``scaffold``; an unknown kind is a ``ValueError``). Hidden ones are left out."""
    wanted = tuple(KINDS) if kinds is None else tuple(k for k in KINDS if k in set(kinds))
    unknown = set(kinds or ()) - set(KINDS)
    if unknown:
        raise ValueError("unknown requisition kind")
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    found: list[RequisitionRow] = []
    for kind in wanted:
        record_type = KINDS[kind]
        statement = text(
            "SELECT t.id, r.key, t.kind, t.subject, COALESCE(r.status, :requested) AS state, "
            "t.requester, t.priority, t.need_by, t.for_record_id, t.approved_by, "
            f"t.work_order_id, r.version FROM {TABLES[record_type]} t "
            "JOIN cur_core_record r ON r.id = t.id "
            f"WHERE t.for_record_id = :record AND r.voided = :no AND {visible} "
            f"AND COALESCE(r.status, :requested) NOT IN ({_FINAL}) "
            "ORDER BY r.key, r.id LIMIT :limit"
        )
        rows = conn.execute(
            statement,
            {
                "record": record_id,
                "no": False,
                "requested": ST_REQUESTED,
                "limit": MAX_ROWS + 1,
                **extra,
            },
        )
        found.extend(
            RequisitionRow(
                id=str(row.id),
                key=str(row.key),
                kind=str(row.kind),
                record_type=record_type,
                subject=str(row.subject),
                state=str(row.state),
                requester=str(row.requester),
                priority=str(row.priority),
                need_by=_opt(row.need_by),
                for_record_id=_opt(row.for_record_id),
                approved_by=_opt(row.approved_by),
                work_order_id=_opt(row.work_order_id),
                version=int(row.version),
            )
            for row in rows
        )
        if len(found) > MAX_ROWS:
            raise ValueError(MSG_TOO_MANY)
    return sorted(found, key=lambda r: (r.key, r.id))


def work_order_for(
    conn: Connection,
    requisition_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> WorkOrderRow | None:
    """The work order of a requisition; ``None`` when it has none (not approved) or when the
    requisition or the work order is hidden from the viewer."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    hidden_requisition, extra_requisition = confidentiality.not_hidden_each(
        "w.requisition_id", viewer
    )
    row = conn.execute(
        text(
            "SELECT w.id, r.key, w.requisition_id, w.work_kind, COALESCE(r.status, :open) AS state, "
            "w.assigned_to, w.planned_start, w.planned_finish, w.actual_start, w.actual_finish, "
            f"w.hours_planned, w.hours_actual, r.version FROM {WORK_ORDER_TABLE} w "
            "JOIN cur_core_record r ON r.id = w.id "
            f"WHERE w.requisition_id = :requisition AND r.voided = :no AND {visible} "
            f"AND {hidden_requisition} ORDER BY r.key, r.id LIMIT 1"
        ),
        {"requisition": requisition_id, "no": False, "open": ST_OPEN, **extra, **extra_requisition},
    ).first()
    if row is None:
        return None
    return WorkOrderRow(
        id=str(row.id),
        key=str(row.key),
        requisition_id=str(row.requisition_id),
        work_kind=str(row.work_kind),
        state=str(row.state),
        assigned_to=_opt(row.assigned_to),
        planned_start=_opt(row.planned_start),
        planned_finish=_opt(row.planned_finish),
        actual_start=_opt(row.actual_start),
        actual_finish=_opt(row.actual_finish),
        hours_planned=_opt(row.hours_planned),
        hours_actual=_opt(row.hours_actual),
        version=int(row.version),
    )


__all__ = [
    "MAX_ROWS",
    "RequisitionRow",
    "WorkOrderRow",
    "open_requisitions_for",
    "work_order_for",
]
