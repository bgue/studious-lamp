"""Read views of the requisitions module: the requisition list and detail, the work order list and
detail. Nothing here writes, and no access word is checked (the entry points check it).

Every function takes ``viewer=`` keyword-only; its default is ``confidentiality.LOWEST``, never the
ambient viewer. The hidden filter is the one ``api.py`` applies, inside the statement and before
``LIMIT``: a hidden requisition (or the work order of one) is absent from lists, and its detail is
``None``, as a missing one is. Limits are clamped to 1..``MAX_LIMIT``; an unknown kind is a
``ValueError``. A list runs at most one statement per kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection, Row, text
from tl_core import confidentiality

from tl_mod_requisitions.api import RequisitionRow, WorkOrderRow, work_order_for
from tl_mod_requisitions.names import (
    GENERAL,
    KINDS,
    LABOR,
    MATERIAL,
    REQUISITION_TYPES,
    SCAFFOLD,
    ST_OPEN,
    ST_REQUESTED,
    TABLES,
    WORK_ORDER_TABLE,
)

MAX_LIMIT: Final = 500
MIN_LIMIT: Final = 1
MSG_UNKNOWN_KIND: Final = "unknown requisition kind"

#: The kind-specific columns of each requisition table, as stored (``requisitions`` DDL).
KIND_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    LABOR: (
        "craft",
        "classification",
        "headcount",
        "start_date",
        "end_date",
        "shift",
        "requirements",
    ),
    MATERIAL: ("from_location_id", "lines_json"),
    GENERAL: ("general_type",),
    SCAFFOLD: (
        "purpose",
        "elevation",
        "gridline",
        "length_m",
        "width_m",
        "height_m",
        "load_class",
        "duration_days",
    ),
}

_REQUISITION_COLUMNS: Final = (
    "t.id, r.key, t.kind, t.subject, COALESCE(r.status, :requested) AS state, "
    "t.requester, t.priority, t.need_by, t.for_record_id, t.approved_by, "
    "t.work_order_id, r.version"
)
_WORK_ORDER_COLUMNS: Final = (
    "w.id, r.key, w.requisition_id, w.work_kind, COALESCE(r.status, :open) AS state, "
    "w.assigned_to, w.planned_start, w.planned_finish, w.actual_start, w.actual_finish, "
    "w.hours_planned, w.hours_actual, r.version"
)


@dataclass(frozen=True)
class RequisitionDetail:
    """A requisition with its kind-specific columns as stored, and its work order if it has one."""

    row: RequisitionRow
    fields: dict[str, str | None]
    work_order: WorkOrderRow | None


@dataclass(frozen=True)
class WorkOrderDetail:
    """A work order, with the key of the requisition it belongs to."""

    row: WorkOrderRow
    requisition_key: str


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


def _clamp(limit: int) -> int:
    return min(max(int(limit), MIN_LIMIT), MAX_LIMIT)


def _requisition(record_type: str, row: Row[Any]) -> RequisitionRow:
    return RequisitionRow(
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


def _work_order(row: Row[Any]) -> WorkOrderRow:
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


def requisition_list(
    conn: Connection,
    scope: str,
    *,
    kind: str | None = None,
    state: str | None = None,
    requester: str | None = None,
    for_record: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[RequisitionRow]:
    """The requisitions of ``scope`` (all kinds, or one ``kind``), by key, that match the filters.
    ``for_record`` is a record id (the record the requisition serves). Hidden ones are left out."""
    if kind is not None and kind not in KINDS:
        raise ValueError(MSG_UNKNOWN_KIND)
    wanted = tuple(KINDS.values()) if kind is None else (KINDS[kind],)
    take = _clamp(limit)
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    found: list[RequisitionRow] = []
    for record_type in wanted:
        conditions = ["r.scope = :scope", "r.voided = :no", visible]
        params: dict[str, Any] = {
            "scope": scope,
            "no": False,
            "requested": ST_REQUESTED,
            "limit": take,
            **extra,
        }
        if state is not None:
            conditions.append("COALESCE(r.status, :requested) = :state")
            params["state"] = state
        if requester is not None:
            conditions.append("t.requester = :requester")
            params["requester"] = requester
        if for_record is not None:
            conditions.append("t.for_record_id = :record")
            params["record"] = for_record
        statement = text(
            f"SELECT {_REQUISITION_COLUMNS} FROM {TABLES[record_type]} t "
            "JOIN cur_core_record r ON r.id = t.id "
            f"WHERE {' AND '.join(conditions)} ORDER BY r.key, r.id LIMIT :limit"
        )
        found.extend(_requisition(record_type, row) for row in conn.execute(statement, params))
    return sorted(found, key=lambda r: (r.key, r.id))[:take]


def requisition_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> RequisitionDetail | None:
    """The requisition of ``scope`` with this key, with its kind-specific fields and its work
    order. ``None`` when there is no such requisition or the viewer may not read it."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    for record_type in REQUISITION_TYPES:
        columns = KIND_COLUMNS[record_type]
        select = ", ".join(f"t.{column}" for column in columns)
        statement = text(
            f"SELECT {_REQUISITION_COLUMNS}, {select} FROM {TABLES[record_type]} t "
            "JOIN cur_core_record r ON r.id = t.id "
            f"WHERE r.scope = :scope AND r.key = :key AND r.voided = :no AND {visible} LIMIT 1"
        )
        params: dict[str, Any] = {
            "scope": scope,
            "key": key,
            "no": False,
            "requested": ST_REQUESTED,
            **extra,
        }
        row = conn.execute(statement, params).first()
        if row is None:
            continue
        requisition = _requisition(record_type, row)
        return RequisitionDetail(
            row=requisition,
            fields={column: _opt(getattr(row, column)) for column in columns},
            work_order=work_order_for(conn, requisition.id, viewer=viewer),
        )
    return None


def work_order_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    assigned_to: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[WorkOrderRow]:
    """The work orders of ``scope``, by key, that match the filters. A work order of a hidden
    requisition is left out, as is a hidden work order."""
    take = _clamp(limit)
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    hidden_requisition, extra_requisition = confidentiality.not_hidden_each(
        "w.requisition_id", viewer
    )
    conditions = ["r.scope = :scope", "r.voided = :no", visible, hidden_requisition]
    params: dict[str, Any] = {
        "scope": scope,
        "no": False,
        "open": ST_OPEN,
        "limit": take,
        **extra,
        **extra_requisition,
    }
    if state is not None:
        conditions.append("COALESCE(r.status, :open) = :state")
        params["state"] = state
    if assigned_to is not None:
        conditions.append("w.assigned_to = :assigned_to")
        params["assigned_to"] = assigned_to
    statement = text(
        f"SELECT {_WORK_ORDER_COLUMNS} FROM {WORK_ORDER_TABLE} w "
        "JOIN cur_core_record r ON r.id = w.id "
        f"WHERE {' AND '.join(conditions)} ORDER BY r.key, r.id LIMIT :limit"
    )
    return [_work_order(row) for row in conn.execute(statement, params)]


def work_order_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> WorkOrderDetail | None:
    """The work order of ``scope`` with this key, with the key of its requisition. ``None`` when
    there is no such work order or the viewer may not read it (or its requisition)."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    hidden_requisition, extra_requisition = confidentiality.not_hidden_each(
        "w.requisition_id", viewer
    )
    statement = text(
        f"SELECT {_WORK_ORDER_COLUMNS}, q.key AS requisition_key FROM {WORK_ORDER_TABLE} w "
        "JOIN cur_core_record r ON r.id = w.id "
        "JOIN cur_core_record q ON q.id = w.requisition_id "
        f"WHERE r.scope = :scope AND r.key = :key AND r.voided = :no AND {visible} "
        f"AND {hidden_requisition} LIMIT 1"
    )
    params: dict[str, Any] = {
        "scope": scope,
        "key": key,
        "no": False,
        "open": ST_OPEN,
        **extra,
        **extra_requisition,
    }
    row = conn.execute(statement, params).first()
    if row is None:
        return None
    return WorkOrderDetail(row=_work_order(row), requisition_key=str(row.requisition_key))


__all__ = [
    "KIND_COLUMNS",
    "MAX_LIMIT",
    "RequisitionDetail",
    "WorkOrderDetail",
    "requisition_detail",
    "requisition_list",
    "work_order_detail",
    "work_order_list",
]
