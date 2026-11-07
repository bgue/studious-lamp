"""From a ledger event to the IWPs to evaluate (F3): the subscriber of the watched record types.

``on_event(uow, event)`` is the hook the module registers (C2 glue). It is a system job's code:
it reads keys only (ids, a work package column), never a record's text. Own events (source
``job:awp.readiness``, ``IWP.ReadinessEvaluated``, ``IWP.Ready``) are ignored, so an evaluation
never asks for the next one.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import Connection, text
from tl_core.ledger import Event
from tl_core.readiness.registry import load_checks
from tl_core.uow import UnitOfWork

from tl_mod_awp.common import has_table
from tl_mod_awp.names import (
    CONSTRAINT_TABLE,
    CONSTRAINT_TYPE,
    IWP,
    IWP_CHECK,
    IWP_READINESS_EVALUATED,
    IWP_READY,
    IWP_READY_EVENT,
    READINESS_SOURCE,
)
from tl_mod_awp.readiness.engine import Checks, request

#: Most IWPs the fallback queues for one event.
FALLBACK_CAP: Final = 200
#: Record types whose table points to an IWP by ``work_package_id`` (the materials take-off
#: line; the table belongs to the materials module, which awp never imports: names only).
WORK_PACKAGE_TABLES: Final = {"materials.MTOLine": "cur_materials_mto_line"}
WORK_PACKAGE_COLUMN: Final = "work_package_id"
_OWN: Final = frozenset({IWP_READINESS_EVALUATED, IWP_READY_EVENT})
_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")
_SUBJECT_SQL = text(f"SELECT subject_id FROM {CONSTRAINT_TABLE} WHERE id = :id")
_FALLBACK_SQL = text(
    "SELECT id FROM cur_core_record WHERE scope = :scope AND type = :type AND voided = :no "
    "AND status IN (:check, :ready) ORDER BY id LIMIT :limit"
)


def _is_iwp(conn: Connection, record_id: str) -> bool:
    return conn.execute(_TYPE_SQL, {"id": record_id}).scalar_one_or_none() == IWP


def _mapped(conn: Connection, event: Event) -> tuple[bool, str | None]:
    """``(has a mapping, the IWP id or None)`` for an event of a watched, non-IWP type."""
    if event.stream_type == CONSTRAINT_TYPE:
        found = conn.execute(_SUBJECT_SQL, {"id": event.stream_id}).scalar_one_or_none()
        subject = found if found is not None else event.payload.get("subject_id")
        return True, (str(subject) if subject and _is_iwp(conn, str(subject)) else None)
    table = WORK_PACKAGE_TABLES.get(event.stream_type)
    if table is None or not has_table(conn, table):
        return False, None
    sql = text(f"SELECT {WORK_PACKAGE_COLUMN} FROM {table} WHERE id = :id")
    found = conn.execute(sql, {"id": event.stream_id}).scalar_one_or_none()
    return True, (str(found) if found and _is_iwp(conn, str(found)) else None)


def fallback_ids(conn: Connection, scope: str) -> list[str]:
    """The IWPs of ``scope`` in Constraint check or Ready, at most ``FALLBACK_CAP``."""
    rows = conn.execute(
        _FALLBACK_SQL,
        {
            "scope": scope,
            "type": IWP,
            "no": False,
            "check": IWP_CHECK,
            "ready": IWP_READY,
            "limit": FALLBACK_CAP,
        },
    )
    return [str(r.id) for r in rows]


def on_event(uow: UnitOfWork, event: Event, checks: Checks | None = None) -> int:
    """Queue the evaluations an event asks for; the number queued."""
    if event.source == READINESS_SOURCE or event.event_type in _OWN:
        return 0
    found = load_checks() if checks is None else checks
    watched = frozenset().union(*(c.watches for c in found.values()))
    if event.stream_type not in watched:
        return 0
    conn = uow.conn()
    if event.stream_type == IWP:
        return request(uow, [event.stream_id], reason=event.event_type)
    mapped, iwp_id = _mapped(conn, event)
    if mapped:
        return 0 if iwp_id is None else request(uow, [iwp_id], reason=event.event_type)
    return request(uow, fallback_ids(conn, event.scope), reason=event.event_type)


__all__ = ["FALLBACK_CAP", "fallback_ids", "on_event"]
