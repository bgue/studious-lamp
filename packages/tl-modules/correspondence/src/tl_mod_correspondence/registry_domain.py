"""Reading the domain data of Technical and Commercial items (P1-I6).

A Technical or Commercial item is a row of the item table (``registry.ItemRow``: number, parties,
dates, class, thread, clocks) and a row of its domain table, joined on ``id``. Every function here
takes a connection and returns frozen rows. They apply the viewer's confidentiality exactly as
``registry`` does (ADR-0016): an item the viewer may not read is absent from a list and ``None``
from a ``get`` or ``find``, whatever the table says. Nothing here writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_correspondence.names import (
    COMMERCIAL,
    COMMERCIAL_TABLE,
    CORRESPONDENCE_VIEW,
    TECHNICAL,
    TECHNICAL_TABLE,
)
from tl_mod_correspondence.registry import _ITEM_COLUMNS, ItemRow, _hidden, _item, _json

_ITEM_I = ", ".join(f"i.{c.strip()}" for c in _ITEM_COLUMNS.split(","))


# --- Technical -------------------------------------------------------------------------------


@dataclass(frozen=True)
class TechnicalData:
    question: str
    proposed_solution: str | None
    discipline: str | None
    required_by: str | None
    potential_cost_impact: str
    potential_schedule_impact: str
    answer: str | None
    answered_on: str | None
    answer_cost_impact: str | None
    answer_schedule_impact: str | None
    answer_item_id: str | None
    answering_revision_id: str | None
    review_decision: str | None
    reviewed_on: str | None
    review_note: str | None


@dataclass(frozen=True)
class TechnicalRow:
    """An RFI, a technical query or a deviation request: the item and its domain data."""

    item: ItemRow
    data: TechnicalData


_TECH_COLUMNS = (
    "t.question, t.proposed_solution, t.discipline, t.required_by, t.potential_cost_impact, "
    "t.potential_schedule_impact, t.answer, t.answered_on, t.answer_cost_impact, "
    "t.answer_schedule_impact, t.answer_item_id, t.answering_revision_id, t.review_decision, "
    "t.reviewed_on, t.review_note"
)
_TECH_FROM = (
    f"FROM {CORRESPONDENCE_VIEW} i JOIN {TECHNICAL_TABLE} t ON t.id = i.id "
    f"WHERE i.record_type = '{TECHNICAL}'"
)


def _technical(row: Any) -> TechnicalRow:
    return TechnicalRow(
        item=_item(row),
        data=TechnicalData(
            question=row.question,
            proposed_solution=row.proposed_solution,
            discipline=row.discipline,
            required_by=row.required_by,
            potential_cost_impact=row.potential_cost_impact,
            potential_schedule_impact=row.potential_schedule_impact,
            answer=row.answer,
            answered_on=row.answered_on,
            answer_cost_impact=row.answer_cost_impact,
            answer_schedule_impact=row.answer_schedule_impact,
            answer_item_id=row.answer_item_id,
            answering_revision_id=row.answering_revision_id,
            review_decision=row.review_decision,
            reviewed_on=row.reviewed_on,
            review_note=row.review_note,
        ),
    )


def get_technical(conn: Connection, item_id: str) -> TechnicalRow | None:
    """The Technical item with this id, or ``None`` (missing, not Technical, or hidden)."""
    row = conn.execute(
        text(f"SELECT {_ITEM_I}, {_TECH_COLUMNS} {_TECH_FROM} AND i.id = :id"), {"id": item_id}
    ).first()
    return None if row is None or _hidden(conn, item_id) else _technical(row)


def find_technical(conn: Connection, scope: str, number: str) -> TechnicalRow | None:
    """The Technical item of this number in the scope, under the same rule as ``get_technical``."""
    row = conn.execute(
        text(
            f"SELECT {_ITEM_I}, {_TECH_COLUMNS} {_TECH_FROM} "
            "AND i.scope = :scope AND i.number = :number"
        ),
        {"scope": scope, "number": number},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _technical(row)


def list_technical(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    discipline: str | None = None,
    open_only: bool = False,
    include_void: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[TechnicalRow]:
    """The Technical items of a scope the viewer may read, newest number first.

    ``open_only`` keeps the items that are not Closed or Void. A void item is left out unless
    ``include_void``.
    """
    visible, params = confidentiality.not_hidden("i.id")
    sql = f"SELECT {_ITEM_I}, {_TECH_COLUMNS} {_TECH_FROM} AND i.scope = :scope AND {visible}"
    params = {**params, "scope": scope, "limit": limit, "offset": offset}
    for column, value in (("i.subtype", subtype), ("t.discipline", discipline)):
        if value is not None:
            key = column.split(".")[1]
            sql += f" AND {column} = :{key}"
            params[key] = value
    if state is not None:
        sql += " AND COALESCE(i.status, 'Draft') = :state"
        params["state"] = state
    if open_only:
        sql += " AND COALESCE(i.status, 'Draft') NOT IN ('Closed', 'Void')"
    if not include_void:
        sql += " AND COALESCE(i.status, 'Draft') <> 'Void'"
    sql += " ORDER BY i.number DESC LIMIT :limit OFFSET :offset"
    return [_technical(r) for r in conn.execute(text(sql), params).all()]


# --- Commercial ------------------------------------------------------------------------------


@dataclass(frozen=True)
class CommercialData:
    contract_clause_id: str | None
    aware_on: str | None
    derived_from_id: str | None
    currency: str | None
    estimated_value: str | None
    estimated_hours: str | None
    cost_code_impacts: list[dict[str, Any]]
    schedule_impact_days: int | None
    schedule_impact_note: str | None
    entitlement_basis: str | None
    assessed_value: str | None
    assessed_on: str | None
    assessment_status: str | None
    assessment_note: str | None


@dataclass(frozen=True)
class CommercialRow:
    """A Commercial item: the item and its domain data."""

    item: ItemRow
    data: CommercialData


_COMM_COLUMNS = (
    "t.contract_clause_id, t.aware_on, t.derived_from_id, t.currency, t.estimated_value, "
    "t.estimated_hours, t.cost_code_impacts_json, t.schedule_impact_days, "
    "t.schedule_impact_note, t.entitlement_basis, t.assessed_value, t.assessed_on, "
    "t.assessment_status, t.assessment_note"
)
_COMM_FROM = (
    f"FROM {CORRESPONDENCE_VIEW} i JOIN {COMMERCIAL_TABLE} t ON t.id = i.id "
    f"WHERE i.record_type = '{COMMERCIAL}'"
)


def _commercial(row: Any) -> CommercialRow:
    impacts = _json(row.cost_code_impacts_json, [])
    return CommercialRow(
        item=_item(row),
        data=CommercialData(
            contract_clause_id=row.contract_clause_id,
            aware_on=row.aware_on,
            derived_from_id=row.derived_from_id,
            currency=row.currency,
            estimated_value=row.estimated_value,
            estimated_hours=row.estimated_hours,
            cost_code_impacts=[dict(i) for i in impacts] if isinstance(impacts, list) else [],
            schedule_impact_days=row.schedule_impact_days,
            schedule_impact_note=row.schedule_impact_note,
            entitlement_basis=row.entitlement_basis,
            assessed_value=row.assessed_value,
            assessed_on=row.assessed_on,
            assessment_status=row.assessment_status,
            assessment_note=row.assessment_note,
        ),
    )


def get_commercial(conn: Connection, item_id: str) -> CommercialRow | None:
    """The Commercial item with this id, or ``None`` (missing, not Commercial, or hidden)."""
    row = conn.execute(
        text(f"SELECT {_ITEM_I}, {_COMM_COLUMNS} {_COMM_FROM} AND i.id = :id"), {"id": item_id}
    ).first()
    return None if row is None or _hidden(conn, item_id) else _commercial(row)


def find_commercial(conn: Connection, scope: str, number: str) -> CommercialRow | None:
    """The Commercial item of this number in the scope (the rule of ``get_commercial``)."""
    row = conn.execute(
        text(
            f"SELECT {_ITEM_I}, {_COMM_COLUMNS} {_COMM_FROM} "
            "AND i.scope = :scope AND i.number = :number"
        ),
        {"scope": scope, "number": number},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _commercial(row)


def list_commercial(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    assessment_status: str | None = None,
    clause_id: str | None = None,
    open_only: bool = False,
    include_void: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[CommercialRow]:
    """The Commercial items of a scope the viewer may read, newest number first.

    ``open_only`` keeps the items that are not Closed or Void. A void item is left out unless
    ``include_void``.
    """
    visible, params = confidentiality.not_hidden("i.id")
    sql = f"SELECT {_ITEM_I}, {_COMM_COLUMNS} {_COMM_FROM} AND i.scope = :scope AND {visible}"
    params = {**params, "scope": scope, "limit": limit, "offset": offset}
    for column, key, value in (
        ("i.subtype", "subtype", subtype),
        ("t.assessment_status", "assessment_status", assessment_status),
        ("t.contract_clause_id", "clause_id", clause_id),
    ):
        if value is not None:
            sql += f" AND {column} = :{key}"
            params[key] = value
    if state is not None:
        sql += " AND COALESCE(i.status, 'Draft') = :state"
        params["state"] = state
    if open_only:
        sql += " AND COALESCE(i.status, 'Draft') NOT IN ('Closed', 'Void')"
    if not include_void:
        sql += " AND COALESCE(i.status, 'Draft') <> 'Void'"
    sql += " ORDER BY i.number DESC LIMIT :limit OFFSET :offset"
    return [_commercial(r) for r in conn.execute(text(sql), params).all()]


def derived_from_commercial(conn: Connection, source_id: str) -> list[CommercialRow]:
    """The Commercial items raised from ``source_id`` (an RFI) that the viewer may read."""
    visible, params = confidentiality.not_hidden("i.id")
    sql = (
        f"SELECT {_ITEM_I}, {_COMM_COLUMNS} {_COMM_FROM} AND t.derived_from_id = :source "
        f"AND {visible} ORDER BY i.number"
    )
    return [_commercial(r) for r in conn.execute(text(sql), {**params, "source": source_id}).all()]
