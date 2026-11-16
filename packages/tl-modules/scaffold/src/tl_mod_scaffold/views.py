"""Read views of the scaffold register (P2-I4B T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``). Nothing here reads
the clock: the due questions take ``today`` (``YYYY-MM-DD``).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from tl_core import confidentiality

from tl_mod_scaffold import names
from tl_mod_scaffold.rules import STANDING_STATES

MAX_LIMIT: Final = 500
EXPORT_FORMATS: Final = ("csv", "jsonl")
#: The exported columns, in order (the ``ScaffoldRow`` fields without ``id``).
EXPORT_COLUMNS: Final = (
    "key",
    "subject",
    "state",
    "tag",
    "tagged_on",
    "last_inspected_on",
    "next_due_on",
    "location",
    "elevation",
    "gridline",
    "load_class",
    "request_key",
)
_STUB: Final = "T01 fills this body"
MSG_STATE: Final = "unknown scaffold state"
MSG_TAG: Final = "unknown tag colour"
MSG_OVERDUE: Final = "overdue needs today (YYYY-MM-DD)"
MSG_FORMAT: Final = "unknown export format"
_STATES: Final = (
    names.REQUESTED,
    names.DESIGNED_STATE,
    names.ERECTING_STATE,
    names.INSPECTED_STATE,
    names.IN_USE,
    names.MODIFY,
    names.DISMANTLE,
    names.REMOVED,
)
_TAGS: Final = (names.GREEN, names.YELLOW, names.RED)
#: The standing states as SQL literals (constants from ``rules``, never user input).
_STANDING_SQL: Final = ", ".join(f"'{state}'" for state in sorted(STANDING_STATES))
#: The scaffold join, its request (LEFT: a row may lack one) and the record it serves (LEFT).
_FROM: Final = (
    f"FROM {names.SCAFFOLD_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "LEFT JOIN cur_core_record rq ON rq.id = t.request_id "
    "LEFT JOIN cur_core_record sv ON sv.id = t.for_record_id "
)
_STATE: Final = f"COALESCE(r.status, '{names.REQUESTED}')"
_ROW_COLUMNS: Final = (
    "r.id, r.key, r.title, "
    f"{_STATE} AS state, t.tag, t.tagged_on, t.last_inspected_on, t.next_due_on, "
    "t.location_text AS location, t.elevation, t.gridline, t.load_class, "
    "rq.key AS request_key"
)
_GUARD: Final = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class ScaffoldRow:
    id: str  # the record id, for commands; never printed or exported
    key: str
    subject: str
    state: str
    tag: str | None
    tagged_on: str | None
    last_inspected_on: str | None
    next_due_on: str | None
    location: str | None  # the row's location_text
    elevation: str | None
    gridline: str | None
    load_class: str | None
    request_key: str | None  # the key of the scaffold request it was registered from


@dataclass(frozen=True)
class InspectionRow:
    key: str
    inspected_on: str
    inspector: str
    result: str
    tag: str | None
    note: str | None


@dataclass(frozen=True)
class ScaffoldDetail:
    row: ScaffoldRow
    inspection_count: int
    modify_reason: str | None
    dismantle_reason: str | None
    for_key: str | None  # the key of the record the request serves (an IWP)
    version: int
    inspections: list[InspectionRow]  # oldest first (inspected_on, key)


@dataclass(frozen=True)
class ScaffoldPage:
    rows: list[ScaffoldRow]
    total: int  # visible rows matching the filters, before the limit


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def _row(raw: RowMapping) -> ScaffoldRow:
    return ScaffoldRow(
        id=str(raw["id"]),
        key=str(raw["key"]),
        subject=str(raw["title"]),
        state=str(raw["state"]),
        tag=_text(raw["tag"]),
        tagged_on=_text(raw["tagged_on"]),
        last_inspected_on=_text(raw["last_inspected_on"]),
        next_due_on=_text(raw["next_due_on"]),
        location=_text(raw["location"]),
        elevation=_text(raw["elevation"]),
        gridline=_text(raw["gridline"]),
        load_class=_text(raw["load_class"]),
        request_key=_text(raw["request_key"]),
    )


def _guard(value: Any) -> Any:
    """A text cell a spreadsheet would read as a formula gets a leading quote (CSV only)."""
    if isinstance(value, str) and value.startswith(_GUARD):
        return "'" + value
    return value


def scaffold_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    tag: str | None = None,
    overdue: bool = False,
    today: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ScaffoldPage:
    """Visible scaffolds of ``scope`` by key."""
    if state is not None and state not in _STATES:
        raise ValueError(MSG_STATE)
    if tag is not None and tag not in _TAGS:
        raise ValueError(MSG_TAG)
    if overdue and today is None:
        raise ValueError(MSG_OVERDUE)
    params: dict[str, Any] = {"scope": scope, "no": False, "limit": _limit(limit)}
    conds = ["r.scope = :scope", "r.voided = :no"]
    if state is not None:
        conds.append(f"{_STATE} = :state")
        params["state"] = state
    if tag is not None:
        conds.append("t.tag = :tag")
        params["tag"] = tag
    if overdue:
        conds.append(f"{_STATE} IN ({_STANDING_SQL}) AND t.next_due_on < :today")
        params["today"] = today
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    conds.append(visible)
    params.update(extra)
    where = " AND ".join(conds)
    total = conn.execute(text(f"SELECT COUNT(*) AS n {_FROM} WHERE {where}"), params).scalar_one()
    raws = conn.execute(
        text(f"SELECT {_ROW_COLUMNS} {_FROM} WHERE {where} ORDER BY r.key, r.id LIMIT :limit"),
        params,
    ).mappings()
    return ScaffoldPage(rows=[_row(raw) for raw in raws], total=int(total))


def scaffold_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ScaffoldDetail | None:
    """One scaffold with its inspections; ``None`` when absent, in another project or hidden."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    statement = text(
        f"SELECT {_ROW_COLUMNS}, r.version, t.inspection_count, t.modify_reason, "
        "t.dismantle_reason, sv.key AS for_key "
        f"{_FROM} WHERE r.scope = :scope AND r.key = :key AND r.voided = :no AND {visible}"
    )
    params = {"scope": scope, "key": key, "no": False, **extra}
    raw = conn.execute(statement, params).mappings().first()
    if raw is None:
        return None
    # the inspections are read only now: the scaffold has passed the viewer's filter
    found = conn.execute(
        text(
            "SELECT ir.key, i.inspected_on, i.inspector, i.result, i.tag, i.note "
            f"FROM {names.INSPECTION_TABLE} i JOIN cur_core_record ir ON ir.id = i.id "
            "WHERE i.scaffold_id = :scaffold ORDER BY i.inspected_on, ir.key"
        ),
        {"scaffold": str(raw["id"])},
    ).mappings()
    inspections = [
        InspectionRow(
            key=str(item["key"]),
            inspected_on=str(item["inspected_on"]),
            inspector=str(item["inspector"]),
            result=str(item["result"]),
            tag=_text(item["tag"]),
            note=_text(item["note"]),
        )
        for item in found
    ]
    return ScaffoldDetail(
        row=_row(raw),
        inspection_count=int(raw["inspection_count"] or 0),
        modify_reason=_text(raw["modify_reason"]),
        dismantle_reason=_text(raw["dismantle_reason"]),
        for_key=_text(raw["for_key"]),
        version=int(raw["version"]),
        inspections=inspections,
    )


def due_list(
    conn: Connection,
    scope: str,
    today: str,
    *,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[ScaffoldRow]:
    """Standing scaffolds (Inspected, In Use, Modify) whose next inspection is due on or before
    ``today``, soonest due first, then by key."""
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    where = (
        f"r.scope = :scope AND r.voided = :no AND {_STATE} IN ({_STANDING_SQL}) "
        f"AND t.next_due_on <= :today AND {visible}"
    )
    params = {"scope": scope, "no": False, "today": today, "limit": _limit(limit), **extra}
    raws = conn.execute(
        text(
            f"SELECT {_ROW_COLUMNS} {_FROM} WHERE {where} "
            "ORDER BY t.next_due_on, r.key, r.id LIMIT :limit"
        ),
        params,
    ).mappings()
    return [_row(raw) for raw in raws]


def export_rows(rows: Sequence[ScaffoldRow], fmt: str) -> str:
    """The rows as ``csv`` (a header line, ``\\n`` line ends) or ``jsonl``; else ``ValueError``."""
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(EXPORT_COLUMNS)
        for item in rows:
            writer.writerow(["" if value is None else _guard(value) for value in _cells(item)])
        return buf.getvalue()
    if fmt == "jsonl":
        return "".join(
            json.dumps({column: getattr(item, column) for column in EXPORT_COLUMNS}) + "\n"
            for item in rows
        )
    raise ValueError(MSG_FORMAT)


def _cells(item: ScaffoldRow) -> list[Any]:
    return [getattr(item, column) for column in EXPORT_COLUMNS]


__all__ = [
    "EXPORT_COLUMNS",
    "EXPORT_FORMATS",
    "MAX_LIMIT",
    "InspectionRow",
    "ScaffoldDetail",
    "ScaffoldPage",
    "ScaffoldRow",
    "due_list",
    "export_rows",
    "scaffold_detail",
    "scaffold_list",
]
