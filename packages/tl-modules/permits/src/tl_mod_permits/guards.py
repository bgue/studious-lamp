"""The guards of a permit: which states a command takes, and the issue guards (one function).

``issue_guards`` is the one place the blockers are read. Issue, Resume and Revalidate all call it;
nothing copies it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, bindparam, text
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

from tl_mod_permits import rules
from tl_mod_permits.names import (
    ACTIVE,
    APPLIED,
    APPROVED,
    HANDED_BACK,
    ISOLATION,
    LAPSED,
    PERMIT,
    PERMIT_ISOLATION_LINKED,
    PERMIT_ISOLATION_UNLINKED,
    REQUESTED,
    SUSPENDED,
)
from tl_mod_permits.types_table import load_types

GAS_VALID_MINUTES = "permits.gas_test.valid_minutes"
#: The states (Lapsed included, as ``rules.effective_state`` shows it) each command takes.
NEEDS: dict[str, tuple[str, ...]] = {
    "ApprovePermit": (REQUESTED,),
    "RejectPermit": (REQUESTED,),
    "IssuePermit": (APPROVED,),
    "RevalidatePermit": (ACTIVE, LAPSED),
    "SuspendPermit": (ACTIVE, LAPSED),
    "ResumePermit": (SUSPENDED,),
    "HandBackPermit": (ACTIVE, LAPSED, SUSPENDED),
    "ClosePermit": (HANDED_BACK,),
    "CancelPermit": (REQUESTED, APPROVED),
}

#: The stored states in which a permit still needs the isolations it links.
BLOCKS_REMOVAL: tuple[str, ...] = (APPROVED, ACTIVE, SUSPENDED)
_DEPENDENT_EVENTS_SQL = text(
    "SELECT stream_id, event_type, payload FROM events WHERE event_type IN (:linked, :unlinked) "
    "AND CAST(payload AS TEXT) LIKE :pattern ORDER BY seq"
)
_DEPENDENT_STATE_SQL = text(
    "SELECT id, key, scope, status FROM cur_core_record "
    "WHERE id IN :ids AND type = :type AND voided = :voided"
).bindparams(bindparam("ids", expanding=True))
_GAS_SQL = text("SELECT taken_at, result FROM cur_permits_gas_test WHERE permit_id = :id")
_LINK_SQL = text(
    "SELECT event_type, payload FROM events WHERE stream_id = :id AND event_type IN "
    "(:linked, :unlinked) ORDER BY seq"
)
_ISOLATION_SQL = text(
    "SELECT id, status FROM cur_core_record WHERE id IN :ids AND type = :type AND voided = :voided"
).bindparams(bindparam("ids", expanding=True))


def as_time(value: Any) -> datetime:
    """A stored time as an aware datetime (SQLite keeps text, Postgres a timestamp)."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def ticked_ids(permit: Mapping[str, Any]) -> list[str]:
    """The ids of the precautions ticked on ``permit`` (its ``precautions_json``)."""
    raw = permit["precautions_json"]
    items = json.loads(raw) if isinstance(raw, str) else raw
    return [str(item["id"]) for item in items]


def linked_isolations(conn: Connection, permit_id: str) -> list[str]:
    """The isolations the permit's own events link and have not unlinked, oldest first."""
    live: dict[str, None] = {}
    for kind, payload in conn.execute(
        _LINK_SQL,
        {"id": permit_id, "linked": PERMIT_ISOLATION_LINKED, "unlinked": PERMIT_ISOLATION_UNLINKED},
    ):
        body = json.loads(payload) if isinstance(payload, str) else payload
        if kind == PERMIT_ISOLATION_LINKED:
            live[str(body["isolation_id"])] = None
        else:
            live.pop(str(body["isolation_id"]), None)
    return list(live)


def dependent_permits(conn: Connection, isolation_id: str) -> list[Mapping[str, Any]]:
    """The permits that depend on the isolation: their own events link it and have not unlinked
    it, and they are Approved, Active or Suspended (Lapsed is an Active permit shown late, so it
    counts as Active). Rows carry ``id``, ``key``, ``scope`` and ``status``, oldest link first.

    Two statements, whatever the number of permits: one over the link events (narrowed by a text
    match on the isolation id, then read as JSON), one for the states of the permits found. The
    rows are not filtered for the viewer: the caller decides what to show of each."""
    live: dict[str, None] = {}
    for stream, kind, payload in conn.execute(
        _DEPENDENT_EVENTS_SQL,
        {
            "linked": PERMIT_ISOLATION_LINKED,
            "unlinked": PERMIT_ISOLATION_UNLINKED,
            "pattern": f"%{isolation_id}%",
        },
    ):
        body = json.loads(payload) if isinstance(payload, str) else payload
        if str(body["isolation_id"]) != isolation_id:
            continue
        if kind == PERMIT_ISOLATION_LINKED:
            live[str(stream)] = None
        else:
            live.pop(str(stream), None)
    if not live:
        return []
    rows = conn.execute(
        _DEPENDENT_STATE_SQL, {"ids": list(live), "type": PERMIT, "voided": False}
    ).mappings()
    states = {str(r["id"]): r for r in rows}
    found: list[Mapping[str, Any]] = []
    for permit_id in live:
        row = states.get(permit_id)
        status = REQUESTED if row is None or row["status"] is None else str(row["status"])
        if row is not None and status in BLOCKS_REMOVAL:
            found.append(
                {"id": permit_id, "key": row["key"], "scope": row["scope"], "status": status}
            )
    return found


def isolation_states(conn: Connection, permit_id: str) -> list[str]:
    ids = linked_isolations(conn, permit_id)
    if not ids:
        return []
    rows = conn.execute(_ISOLATION_SQL, {"ids": ids, "type": ISOLATION, "voided": False}).all()
    return [APPLIED if status is None else str(status) for _id, status in rows]


def issue_guards(conn: Connection, permit: Mapping[str, Any], now: datetime) -> list[str]:
    """The blocker codes that refuse to make ``permit`` live now (empty: clean).

    ``permit`` is its row of ``cur_permits_permit``; its ``precautions_json`` is the ticked list.
    """
    rule = load_types()[str(permit["permit_type"])]
    project = project_of_scope(str(permit["scope"]))
    minutes = int(value_of(conn, GAS_VALID_MINUTES, project=project))
    tests = [
        (when, str(result))
        for when, result in (
            (as_time(t), r) for t, r in conn.execute(_GAS_SQL, {"id": permit["id"]})
        )
        if when <= now  # a reading dated after now is no evidence yet
    ]
    return rules.issue_blockers(
        needs_gas_test=rule.needs_gas_test,
        needs_isolation=rule.needs_isolation,
        required_precautions=[p.id for p in rule.precautions],
        ticked_precautions=ticked_ids(permit),
        gas_tests=tests,
        isolation_states=isolation_states(conn, str(permit["id"])),
        gas_valid_minutes=minutes,
        now=now,
    )
