"""Read views of permits (P2-PTW T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``, never widened) and
applies the hidden filter before LIMIT and before counting: a hidden record is absent from lists,
its detail is ``None``, counts never include it. Nothing here reads the clock: ``now`` is a
parameter, and an Active permit whose ``valid_until`` has passed is shown as Lapsed through
``rules.effective_state``. Nothing is written and no access word is checked here.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from tl_core import confidentiality
from tl_core.ledger import iso_utc

from tl_mod_permits import rules
from tl_mod_permits.names import ACTIVE, LAPSED, PERMIT_TABLE, REQUESTED

#: The most rows one list returns.
MAX_LIMIT: Final = 500
#: The states a permit is shown in (Lapsed in place of Active when its validity has passed).
SHOWN_STATES: Final = (
    "Requested",
    "Approved",
    "Active",
    "Lapsed",
    "Suspended",
    "Handed back",
    "Closed",
    "Rejected",
    "Cancelled",
)
#: The states of a permit that is live: on the board.
LIVE_STATES: Final = ("Lapsed", "Suspended", "Active")
EXPORT_FORMATS: Final = ("csv", "jsonl")
#: The columns of an export, in order (the register of design section 8).
EXPORT_COLUMNS: Final = (
    "number",
    "type",
    "state",
    "area",
    "holder",
    "issued",
    "valid_until",
    "revalidations",
    "closed",
)


@dataclass(frozen=True)
class PermitRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    subject: str
    permit_type: str
    state: str  # as shown: Lapsed in place of Active
    area: str | None
    holder: str | None
    issued_at: datetime | None
    valid_until: datetime | None
    revalidation_count: int
    closed_by: str | None
    for_key: str | None  # the key of the record the work is for


@dataclass(frozen=True)
class PermitDetail:
    row: PermitRow
    description: str | None
    location_text: str | None
    requested_by: str | None
    needed_from: str | None
    needed_until: str | None
    approved_by: str | None
    issued_by: str | None
    precautions: list[str]  # the ticked precaution ids
    suspend_reason: str | None
    handback_note: str | None
    reject_reason: str | None
    cancel_reason: str | None
    version: int


@dataclass(frozen=True)
class PermitPage:
    rows: list[PermitRow]
    total: int


@dataclass(frozen=True)
class BoardArea:
    area: str | None
    rows: list[PermitRow]  # Lapsed and Suspended first, then by key


@dataclass(frozen=True)
class PermitBoard:
    areas: list[BoardArea]  # by area name, no area last
    counts: dict[str, int]  # live permits shown, by shown state


@dataclass(frozen=True)
class PermitRef:
    """A permit as readiness and the IWP card read it: the state is the stored one."""

    id: str
    key: str
    permit_type: str
    state: str
    valid_until: datetime | None


# The permit row, its record and its workflow state. A permit with no transition yet has no state
# row: it is Requested, as ``handlers.common`` reads it. The stored Active is shown Lapsed when its
# validity has ended at ``:now`` (a NULL end is Lapsed). ``_SHOWN`` is only for a filter or the
# count/board split; the state a row shows is built in ``_row`` by ``rules.effective_state``.
# The for-record is joined for its key only.
_FROM = (
    f"FROM {PERMIT_TABLE} p JOIN cur_core_record r ON r.id = p.id "
    "LEFT JOIN cur_workflow_state w ON w.record_id = p.id "
    "LEFT JOIN cur_core_record f ON f.id = p.for_record_id "
)
_STORED = f"COALESCE(w.state, '{REQUESTED}')"
_SHOWN = (
    f"CASE WHEN {_STORED} = '{ACTIVE}' AND (p.valid_until IS NULL OR p.valid_until <= :now) "
    f"THEN '{LAPSED}' ELSE {_STORED} END"
)
_ROW_COLUMNS = (
    f"r.id, r.key, r.title, {_STORED} AS state, p.permit_type, p.area, p.holder, "
    "p.issued_at, p.valid_until, p.revalidation_count, p.closed_by, f.key AS for_key"
)
_DETAIL_COLUMNS = (
    "r.description, r.version, p.location_text, p.requested_by, p.needed_from, p.needed_until, "
    "p.approved_by, p.issued_by, p.precautions_json, p.suspend_reason, p.handback_note, "
    "p.reject_reason, p.cancel_reason"
)
_LIVE_IN = "(" + ", ".join(f"'{state}'" for state in LIVE_STATES) + ")"


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _precaution_id(item: Any) -> str:
    """A ticked precaution as its id (a stored tick is ``{"id", "text"}``; a bare id is kept)."""
    return str(item["id"]) if isinstance(item, dict) else str(item)


def _when(value: Any) -> datetime | None:
    """A stored time (UTC text) as an aware datetime."""
    if value is None:
        return None
    moment = datetime.fromisoformat(str(value))
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _row(raw: RowMapping, now: datetime) -> PermitRow:
    valid_until = _when(raw["valid_until"])
    return PermitRow(
        id=str(raw["id"]),
        key=str(raw["key"]),
        subject=str(raw["title"]),
        permit_type=str(raw["permit_type"]),
        state=rules.effective_state(str(raw["state"]), valid_until, now),
        area=_text(raw["area"]),
        holder=_text(raw["holder"]),
        issued_at=_when(raw["issued_at"]),
        valid_until=valid_until,
        revalidation_count=int(raw["revalidation_count"] or 0),
        closed_by=_text(raw["closed_by"]),
        for_key=_text(raw["for_key"]),
    )


def _scoped(
    scope: str, now: datetime, viewer: confidentiality.Viewer
) -> tuple[list[str], dict[str, Any]]:
    """The conditions every read shares: the scope, not voided, the viewer's hidden filter."""
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    conds = ["p.scope = :scope", "r.voided = :no", visible]
    params: dict[str, Any] = {"scope": scope, "no": False, "now": iso_utc(now), **extra}
    return conds, params


def permit_list(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    state: str | None = None,
    permit_type: str | None = None,
    area: str | None = None,
    holder: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitPage:
    """Permits of ``scope`` by key; ``state`` is a shown state (``Lapsed`` and ``Active`` split
    an Active permit at ``now``); ``total`` counts the rows the filters and the viewer leave."""
    conds, params = _scoped(scope, now, viewer)
    filters = {"permit_type": permit_type, "area": area, "holder": holder}
    columns = {"permit_type": "p.permit_type", "area": "p.area", "holder": "p.holder"}
    for name, value in filters.items():
        if value is not None:
            conds.append(f"{columns[name]} = :{name}")
            params[name] = value
    if state is not None:
        conds.append(f"{_SHOWN} = :state")
        params["state"] = state
    params["limit"] = max(1, min(int(limit), MAX_LIMIT))
    params["offset"] = max(0, int(offset))
    where = " AND ".join(conds)
    total = conn.execute(text(f"SELECT COUNT(*) AS n {_FROM} WHERE {where}"), params).scalar_one()
    raws = conn.execute(
        text(
            f"SELECT {_ROW_COLUMNS} {_FROM} WHERE {where} "
            "ORDER BY r.key, r.id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings()
    return PermitPage(rows=[_row(raw, now) for raw in raws], total=int(total))


def permit_detail(
    conn: Connection,
    scope: str,
    number: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitDetail | None:
    """The permit with key ``number``; ``None`` when it is hidden, absent or in another scope."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    statement = text(
        f"SELECT {_ROW_COLUMNS}, {_DETAIL_COLUMNS} {_FROM} "
        "WHERE p.scope = :scope AND r.key = :number AND r.voided = :no "
        f"AND {visible}"
    )
    params: dict[str, Any] = {
        "scope": scope,
        "number": number,
        "no": False,
        "now": iso_utc(now),
        **extra,
    }
    raw = conn.execute(statement, params).mappings().first()
    if raw is None:
        return None
    return PermitDetail(
        row=_row(raw, now),
        description=_text(raw["description"]),
        location_text=_text(raw["location_text"]),
        requested_by=_text(raw["requested_by"]),
        needed_from=_text(raw["needed_from"]),
        needed_until=_text(raw["needed_until"]),
        approved_by=_text(raw["approved_by"]),
        issued_by=_text(raw["issued_by"]),
        precautions=[_precaution_id(p) for p in json.loads(raw["precautions_json"] or "[]")],
        suspend_reason=_text(raw["suspend_reason"]),
        handback_note=_text(raw["handback_note"]),
        reject_reason=_text(raw["reject_reason"]),
        cancel_reason=_text(raw["cancel_reason"]),
        version=int(raw["version"]),
    )


def permit_counts(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Permits of ``scope`` by shown state (every state of ``SHOWN_STATES``, zero included),
    after the hidden filter."""
    conds, params = _scoped(scope, now, viewer)
    where = " AND ".join(conds)
    statement = text(f"SELECT {_SHOWN} AS state, COUNT(*) AS n {_FROM} WHERE {where} GROUP BY 1")
    counts: dict[str, int] = dict.fromkeys(SHOWN_STATES, 0)
    for raw in conn.execute(statement, params).mappings():
        name = str(raw["state"])
        if name in counts:
            counts[name] += int(raw["n"])
    return counts


def permit_board(
    conn: Connection,
    scope: str,
    area: str | None = None,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitBoard:
    """The live permits (Lapsed, Suspended, Active) grouped by area, counts after the hidden
    filter; ``area`` narrows to one."""
    conds, params = _scoped(scope, now, viewer)
    conds.append(f"{_SHOWN} IN {_LIVE_IN}")
    if area is not None:
        conds.append("p.area = :area")
        params["area"] = area
    where = " AND ".join(conds)
    # Lapsed and Suspended first (rank 0), then Active (rank 1), then by key.
    statement = text(
        f"SELECT {_ROW_COLUMNS} {_FROM} WHERE {where} "
        f"ORDER BY (p.area IS NULL), p.area, (CASE WHEN {_SHOWN} = '{ACTIVE}' THEN 1 ELSE 0 END), "
        "r.key, r.id"
    )
    counts: dict[str, int] = dict.fromkeys(LIVE_STATES, 0)
    groups: dict[str | None, list[PermitRow]] = {}
    for raw in conn.execute(statement, params).mappings():
        row = _row(raw, now)
        counts[row.state] += 1
        groups.setdefault(row.area, []).append(row)
    names = sorted(name for name in groups if name is not None)
    areas = [BoardArea(area=name, rows=groups[name]) for name in names]
    if None in groups:
        areas.append(BoardArea(area=None, rows=groups[None]))
    return PermitBoard(areas=areas, counts=counts)


def permits_for(
    conn: Connection,
    record_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[PermitRef]:
    """The permits whose ``for_record_id`` is ``record_id`` (by key); none when the record is
    hidden from the viewer."""
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    statement = text(
        f"SELECT r.id, r.key, p.permit_type, {_STORED} AS state, p.valid_until "
        f"{_FROM} WHERE p.for_record_id = :record_id AND r.voided = :no AND {visible} "
        "ORDER BY r.key, r.id"
    )
    params: dict[str, Any] = {"record_id": record_id, "no": False, **extra}
    return [
        PermitRef(
            id=str(raw["id"]),
            key=str(raw["key"]),
            permit_type=str(raw["permit_type"]),
            state=str(raw["state"]),
            valid_until=_when(raw["valid_until"]),
        )
        for raw in conn.execute(statement, params).mappings()
    ]


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _export_record(row: PermitRow) -> dict[str, Any]:
    return {
        "number": row.key,
        "type": row.permit_type,
        "state": row.state,
        "area": row.area,
        "holder": row.holder,
        "issued": _iso(row.issued_at),
        "valid_until": _iso(row.valid_until),
        "revalidations": row.revalidation_count,
        "closed": row.closed_by,
    }


def export_rows(rows: Sequence[PermitRow], fmt: str) -> str:
    """``rows`` as ``csv`` (a header of ``EXPORT_COLUMNS`` then one line per row, ``\\n`` ends,
    times as ISO text) or ``jsonl`` (one JSON object per row with the same keys); another format
    is a ``ValueError``."""
    if fmt not in EXPORT_FORMATS:
        raise ValueError("export format must be csv or jsonl")
    records = [_export_record(row) for row in rows]
    if fmt == "jsonl":
        return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for record in records:
        writer.writerow([record[column] for column in EXPORT_COLUMNS])
    return buffer.getvalue()
