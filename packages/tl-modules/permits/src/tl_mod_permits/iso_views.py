"""Read views of isolations and gas tests (P2-PTW T02): the isolation register, one isolation, the
gas tests of one permit, and the CSV and JSONL exports of both.

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``, never widened) and
applies the hidden filter before LIMIT and before counting. An isolation is hidden through its own
record or its point record; a gas test through its own record and its permit (a permit for a
restricted record is itself hidden, so its gas tests are). ``depends`` and the permit keys of a
detail count and name only the permits the viewer can read, and are read for every row in one
statement over the link events, then one statement over the permits' states. Nothing here reads
the clock, writes, or checks an access word.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import Connection, bindparam, text
from sqlalchemy.engine import RowMapping
from tl_core import confidentiality

from tl_mod_permits.guards import BLOCKS_REMOVAL
from tl_mod_permits.names import (
    APPLIED,
    PERMIT,
    PERMIT_ISOLATION_LINKED,
    PERMIT_ISOLATION_UNLINKED,
    REQUESTED,
)
from tl_mod_permits.views import EXPORT_FORMATS, _iso, _text, _when

#: The most rows one isolation list returns.
MAX_LIMIT: Final = 500
#: The columns of an isolation export, in order.
ISOLATION_EXPORT_COLUMNS: Final = (
    "number",
    "point",
    "energy",
    "method",
    "lock",
    "tag",
    "state",
    "applied_by",
    "applied",
    "verified_by",
    "verified",
    "depends",
)
#: The columns of a gas test export, in order.
GAS_EXPORT_COLUMNS: Final = (
    "number",
    "taken",
    "result",
    "tester",
    "instrument",
    "o2_pct",
    "lel_pct",
    "h2s_ppm",
    "co_ppm",
    "note",
)


@dataclass(frozen=True)
class IsolationRow:
    id: str  # the record id, for commands
    key: str
    point_text: str
    energy: str
    method: str | None
    lock_number: str | None
    tag_number: str | None
    state: str  # Applied, Verified or Removed (Applied when no transition has run)
    applied_by: str | None
    applied_at: datetime  # every isolation has its Applied event's time
    verified_by: str | None
    verified_at: datetime | None
    depends: int  # the permits the viewer can read that still need this isolation


@dataclass(frozen=True)
class IsolationDetail:
    row: IsolationRow
    point_record_id: str | None
    removed_by: str | None
    removed_at: datetime | None
    version: int
    permits: list[str]  # the keys of the readable dependents, oldest link first


@dataclass(frozen=True)
class IsolationPage:
    rows: list[IsolationRow]
    total: int


@dataclass(frozen=True)
class GasRow:
    key: str
    taken_at: datetime
    result: str
    tester: str
    instrument_text: str | None
    o2_pct: Decimal | None
    lel_pct: Decimal | None
    h2s_ppm: Decimal | None
    co_ppm: Decimal | None
    note: str | None


# The isolation, its record and its state. A stored state is the record's status; none yet is
# Applied, as ``guards.isolation_states`` reads it.
_STATE = f"COALESCE(r.status, '{APPLIED}')"
_FROM = "FROM cur_permits_isolation i JOIN cur_core_record r ON r.id = i.id "
_ROW_COLUMNS = (
    "r.id, r.key, i.point_text, i.energy, i.method, i.lock_number, i.tag_number, "
    f"{_STATE} AS state, i.applied_by, i.applied_at, i.verified_by, i.verified_at"
)
_GAS_FROM = (
    "FROM cur_permits_gas_test g JOIN cur_core_record r ON r.id = g.id "
    "JOIN cur_permits_permit p ON p.id = g.permit_id JOIN cur_core_record pr ON pr.id = p.id "
)


def _decimal(value: Any) -> Decimal | None:
    """A reading as the exact decimal of its text (SQLite returns a NUMERIC as a float)."""
    return None if value is None else Decimal(str(value))


def _required(value: Any, what: str) -> datetime:
    """A stored time the table makes NOT NULL in effect: an absent one is a broken projection."""
    moment = _when(value)
    if moment is None:
        raise LookupError(f"{what} is missing")
    return moment


def _isolation_row(raw: RowMapping, depends: int) -> IsolationRow:
    return IsolationRow(
        id=str(raw["id"]),
        key=str(raw["key"]),
        point_text=str(raw["point_text"]),
        energy=str(raw["energy"]),
        method=_text(raw["method"]),
        lock_number=_text(raw["lock_number"]),
        tag_number=_text(raw["tag_number"]),
        state=str(raw["state"]),
        applied_by=_text(raw["applied_by"]),
        applied_at=_required(raw["applied_at"], f"isolation {raw['key']} applied_at"),
        verified_by=_text(raw["verified_by"]),
        verified_at=_when(raw["verified_at"]),
        depends=depends,
    )


def _depends(
    conn: Connection, isolation_ids: Sequence[str], viewer: confidentiality.Viewer
) -> dict[str, list[str]]:
    """Per isolation id, the keys of the permits that depend on it and that ``viewer`` can read,
    oldest link first. The rule is ``guards.dependent_permits`` (a link not yet unlinked, the
    permit Approved, Active or Suspended), read for all the ids at once: one statement over the
    link events of these isolations, one over the states of the permits they name."""
    wanted = sorted(set(isolation_ids))
    if not wanted:
        return {}
    params: dict[str, Any] = {
        "linked": PERMIT_ISOLATION_LINKED,
        "unlinked": PERMIT_ISOLATION_UNLINKED,
    }
    matches: list[str] = []
    for number, isolation in enumerate(wanted):
        params[f"id{number}"] = f"%{isolation}%"
        matches.append(f"CAST(payload AS TEXT) LIKE :id{number}")
    links = conn.execute(
        text(
            "SELECT stream_id, event_type, payload FROM events "
            "WHERE event_type IN (:linked, :unlinked) AND (" + " OR ".join(matches) + ") "
            "ORDER BY seq"
        ),
        params,
    )
    live: dict[str, dict[str, None]] = {}
    for stream, kind, payload in links:
        body = json.loads(payload) if isinstance(payload, str) else payload
        isolation = str(body["isolation_id"])
        if isolation not in wanted:
            continue
        bucket = live.setdefault(isolation, {})
        if kind == PERMIT_ISOLATION_LINKED:
            bucket[str(stream)] = None
        else:
            bucket.pop(str(stream), None)
    permit_ids = sorted({permit for bucket in live.values() for permit in bucket})
    if not permit_ids:
        return {}
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    states = conn.execute(
        text(
            "SELECT r.id, r.key, r.status FROM cur_core_record r WHERE r.id IN :ids "
            f"AND r.type = :type AND r.voided = :no AND {visible}"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": permit_ids, "type": PERMIT, "no": False, **extra},
    ).mappings()
    blocking: dict[str, str] = {}
    for raw in states:
        status = REQUESTED if raw["status"] is None else str(raw["status"])
        if status in BLOCKS_REMOVAL:
            blocking[str(raw["id"])] = str(raw["key"])
    return {
        isolation: [blocking[permit] for permit in bucket if permit in blocking]
        for isolation, bucket in live.items()
    }


def _isolation_visibility(
    viewer: confidentiality.Viewer,
) -> tuple[str, dict[str, Any]]:
    """The hidden filter of an isolation: its own record, and its point record when it has one."""
    own, own_extra = confidentiality.not_hidden("r.id", viewer)
    point, point_extra = confidentiality.not_hidden_each("i.point_record_id", viewer)
    return f"{own} AND (i.point_record_id IS NULL OR {point})", {**own_extra, **point_extra}


def isolation_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    energy: str | None = None,
    limit: int = 100,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> IsolationPage:
    """Isolations of ``scope`` by key; ``total`` counts the rows the filters and viewer leave."""
    visible, hidden_params = _isolation_visibility(viewer)
    conds = ["i.scope = :scope", "r.voided = :no", visible]
    params: dict[str, Any] = {"scope": scope, "no": False, **hidden_params}
    if state is not None:
        conds.append(f"{_STATE} = :state")
        params["state"] = state
    if energy is not None:
        conds.append("i.energy = :energy")
        params["energy"] = energy
    where = " AND ".join(conds)
    total = conn.execute(text(f"SELECT COUNT(*) AS n {_FROM} WHERE {where}"), params).scalar_one()
    params["limit"] = max(1, min(int(limit), MAX_LIMIT))
    raws = list(
        conn.execute(
            text(f"SELECT {_ROW_COLUMNS} {_FROM} WHERE {where} ORDER BY r.key, r.id LIMIT :limit"),
            params,
        ).mappings()
    )
    depends = _depends(conn, [str(raw["id"]) for raw in raws], viewer)
    rows = [_isolation_row(raw, len(depends.get(str(raw["id"]), []))) for raw in raws]
    return IsolationPage(rows=rows, total=int(total))


def isolation_detail(
    conn: Connection,
    scope: str,
    number: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> IsolationDetail | None:
    """The isolation with key ``number``; ``None`` when it is hidden, absent or in another scope."""
    visible, hidden_params = _isolation_visibility(viewer)
    statement = text(
        f"SELECT {_ROW_COLUMNS}, i.point_record_id, i.removed_by, i.removed_at, r.version "
        f"{_FROM} WHERE i.scope = :scope AND r.key = :number AND r.voided = :no AND {visible}"
    )
    params: dict[str, Any] = {"scope": scope, "number": number, "no": False, **hidden_params}
    found = conn.execute(statement, params).mappings().first()
    if found is None:
        return None
    permits = _depends(conn, [str(found["id"])], viewer).get(str(found["id"]), [])
    return IsolationDetail(
        row=_isolation_row(found, len(permits)),
        point_record_id=_text(found["point_record_id"]),
        removed_by=_text(found["removed_by"]),
        removed_at=_when(found["removed_at"]),
        version=int(found["version"]),
        permits=permits,
    )


def gas_tests_for(
    conn: Connection,
    permit_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[GasRow]:
    """The gas tests of the permit ``permit_id``, newest first; none when the permit is hidden
    from ``viewer`` (a permit for a restricted record is hidden) or absent."""
    own, own_extra = confidentiality.not_hidden("r.id", viewer)
    permit, permit_extra = confidentiality.not_hidden("pr.id", viewer)
    statement = text(
        "SELECT r.key, g.taken_at, g.tester, g.instrument_text, g.o2_pct, g.lel_pct, "
        f"g.h2s_ppm, g.co_ppm, g.result, g.note {_GAS_FROM} "
        f"WHERE g.permit_id = :permit AND r.voided = :no AND pr.voided = :no "
        f"AND {own} AND {permit} ORDER BY g.taken_at DESC, r.key DESC"
    )
    raws = conn.execute(
        statement,
        {"permit": permit_id, "no": False, **own_extra, **permit_extra},
    ).mappings()
    found: list[GasRow] = []
    for raw in raws:
        found.append(
            GasRow(
                key=str(raw["key"]),
                taken_at=_required(raw["taken_at"], f"gas test {raw['key']} taken_at"),
                result=str(raw["result"]),
                tester=str(raw["tester"]),
                instrument_text=_text(raw["instrument_text"]),
                o2_pct=_decimal(raw["o2_pct"]),
                lel_pct=_decimal(raw["lel_pct"]),
                h2s_ppm=_decimal(raw["h2s_ppm"]),
                co_ppm=_decimal(raw["co_ppm"]),
                note=_text(raw["note"]),
            )
        )
    return found


def _isolation_record(row: IsolationRow) -> dict[str, Any]:
    return {
        "number": row.key,
        "point": row.point_text,
        "energy": row.energy,
        "method": row.method,
        "lock": row.lock_number,
        "tag": row.tag_number,
        "state": row.state,
        "applied_by": row.applied_by,
        "applied": _iso(row.applied_at),
        "verified_by": row.verified_by,
        "verified": _iso(row.verified_at),
        "depends": row.depends,
    }


def _gas_record(row: GasRow) -> dict[str, Any]:
    return {
        "number": row.key,
        "taken": _iso(row.taken_at),
        "result": row.result,
        "tester": row.tester,
        "instrument": row.instrument_text,
        "o2_pct": row.o2_pct,
        "lel_pct": row.lel_pct,
        "h2s_ppm": row.h2s_ppm,
        "co_ppm": row.co_ppm,
        "note": row.note,
    }


def _render(records: list[dict[str, Any]], columns: tuple[str, ...], fmt: str) -> str:
    """``records`` as ``csv`` (a header, then one line per record; an empty reading is an empty
    cell) or ``jsonl`` (one object per record; a decimal reading is its exact text)."""
    if fmt not in EXPORT_FORMATS:
        raise ValueError("export format must be csv or jsonl")
    if fmt == "jsonl":
        return "".join(
            json.dumps(record, ensure_ascii=False, default=str) + "\n" for record in records
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for record in records:
        writer.writerow([record[column] for column in columns])
    return buffer.getvalue()


def isolation_export_rows(rows: Sequence[IsolationRow], fmt: str) -> str:
    """``rows`` as ``csv`` or ``jsonl`` (``ISOLATION_EXPORT_COLUMNS``); another format is a
    ``ValueError``."""
    return _render([_isolation_record(row) for row in rows], ISOLATION_EXPORT_COLUMNS, fmt)


def gas_export_rows(rows: Sequence[GasRow], fmt: str) -> str:
    """``rows`` as ``csv`` or ``jsonl`` (``GAS_EXPORT_COLUMNS``); another format is a
    ``ValueError``."""
    return _render([_gas_record(row) for row in rows], GAS_EXPORT_COLUMNS, fmt)
