"""ClockProjector: the ``ResponseClock.*`` events into ``cur_correspondence_response_clock``.

The projector does no arithmetic. ``Started``, ``Resumed`` and ``Restarted`` carry the due date the
clock engine computed (``tl_mod_correspondence.clocks``); the row copies it. ``Paused`` records the
pause, ``Met`` and ``Cancelled`` close the clock, ``Warned`` records the warning threshold crossed
and ``Expired`` marks a running clock past its date. Deterministic. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    CLOCK_CANCELLED,
    CLOCK_EXPIRED,
    CLOCK_MET,
    CLOCK_PAUSED,
    CLOCK_RESTARTED,
    CLOCK_RESUMED,
    CLOCK_STARTED,
    CLOCK_TABLE,
    CLOCK_VIEW,
    CLOCK_WARNED,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {CLOCK_TABLE} (id, scope, item_id, item_number, label, kind, start_on, "
    "duration_days, day_type, calendar, warn_days_json, due_on, state, owner, clause_id, "
    "restarts, last_seq) VALUES (:id, :scope, :item_id, :item_number, :label, :kind, :start_on, "
    ":duration_days, :day_type, :calendar, :warn_days_json, :due_on, 'running', :owner, "
    ":clause_id, 0, :last_seq)"
)
_PAUSED_SQL = text(
    f"UPDATE {CLOCK_TABLE} SET state = 'paused', paused_on = :on, pause_reason = :reason, "
    "last_seq = :last_seq WHERE id = :id"
)
_RESUMED_SQL = text(
    f"UPDATE {CLOCK_TABLE} SET state = 'running', due_on = :due_on, paused_on = NULL, "
    "pause_reason = NULL, last_seq = :last_seq WHERE id = :id"
)
_RESTARTED_SQL = text(
    f"UPDATE {CLOCK_TABLE} SET state = 'running', start_on = :start_on, due_on = :due_on, "
    "paused_on = NULL, pause_reason = NULL, closed_on = NULL, closed_reason = NULL, "
    "warned_level = NULL, restarts = restarts + 1, last_seq = :last_seq WHERE id = :id"
)
_CLOSED_SQL = text(
    f"UPDATE {CLOCK_TABLE} SET state = :state, closed_on = :on, closed_reason = :reason, "
    "paused_on = NULL, pause_reason = NULL, last_seq = :last_seq WHERE id = :id"
)
_WARNED_SQL = text(
    f"UPDATE {CLOCK_TABLE} SET warned_level = :level, last_seq = :last_seq WHERE id = :id"
)
_EXPIRED_SQL = text(
    f"UPDATE {CLOCK_TABLE} SET state = 'expired', last_seq = :last_seq WHERE id = :id"
)


class ClockProjector:
    name = "correspondence_clock"
    handles = frozenset(
        {
            CLOCK_STARTED,
            CLOCK_PAUSED,
            CLOCK_RESUMED,
            CLOCK_RESTARTED,
            CLOCK_MET,
            CLOCK_CANCELLED,
            CLOCK_WARNED,
            CLOCK_EXPIRED,
        }
    )

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CLOCK_TABLE, dialect) + ddl_for(CLOCK_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        et = event.event_type
        base = {"id": event.stream_id, "last_seq": event.seq}
        if et == CLOCK_STARTED:
            conn.execute(
                _INSERT_SQL,
                {
                    **base,
                    "scope": event.scope,
                    "item_id": p["item_id"],
                    "item_number": p["item_number"],
                    "label": p["label"],
                    "kind": p["kind"],
                    "start_on": p["start_on"],
                    "duration_days": p["duration_days"],
                    "day_type": p["day_type"],
                    "calendar": p["calendar"],
                    "warn_days_json": json_text(p.get("warn_days") or []),
                    "due_on": p["due_on"],
                    "owner": p.get("owner"),
                    "clause_id": p.get("clause_id"),
                },
            )
        elif et == CLOCK_PAUSED:
            self._require(
                conn.execute(_PAUSED_SQL, {**base, "on": p["on"], "reason": p["reason"]}).rowcount,
                event,
            )
        elif et == CLOCK_RESUMED:
            self._require(
                conn.execute(_RESUMED_SQL, {**base, "due_on": p["due_on"]}).rowcount, event
            )
        elif et == CLOCK_RESTARTED:
            self._require(
                conn.execute(
                    _RESTARTED_SQL, {**base, "start_on": p["start_on"], "due_on": p["due_on"]}
                ).rowcount,
                event,
            )
        elif et == CLOCK_MET:
            self._require(
                conn.execute(
                    _CLOSED_SQL,
                    {
                        **base,
                        "state": "met",
                        "on": p["on"],
                        "reason": p.get("reason") or p.get("response_id"),
                    },
                ).rowcount,
                event,
            )
        elif et == CLOCK_CANCELLED:
            self._require(
                conn.execute(
                    _CLOSED_SQL,
                    {**base, "state": "cancelled", "on": p["on"], "reason": p["reason"]},
                ).rowcount,
                event,
            )
        elif et == CLOCK_WARNED:
            self._require(conn.execute(_WARNED_SQL, {**base, "level": p["level"]}).rowcount, event)
        elif et == CLOCK_EXPIRED:
            self._require(conn.execute(_EXPIRED_SQL, base).rowcount, event)
        else:
            raise ValueError(f"ClockProjector cannot apply event type: {et}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CLOCK_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CLOCK_TABLE}"))
