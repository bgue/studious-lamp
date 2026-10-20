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
    CLOCK_CANCELLED_STATE,
    CLOCK_EXPIRED,
    CLOCK_EXPIRED_STATE,
    CLOCK_MET,
    CLOCK_MET_STATE,
    CLOCK_PAUSED,
    CLOCK_PAUSED_STATE,
    CLOCK_RESTARTED,
    CLOCK_RESUMED,
    CLOCK_RUNNING,
    CLOCK_STARTED,
    CLOCK_TABLE,
    CLOCK_VIEW,
    CLOCK_WARNED,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record


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
        # The projector does no date arithmetic: due dates come from the events.
        p: dict[str, Any] = event.payload
        et = event.event_type
        base = {"id": event.stream_id, "last_seq": event.seq}
        if et == CLOCK_STARTED:
            conn.execute(
                text(
                    f"INSERT INTO {CLOCK_TABLE} (id, scope, item_id, item_number, label, kind, "
                    "start_on, duration_days, day_type, calendar, due_on, warn_days_json, owner, "
                    "clause_id, state, restarts, last_seq) VALUES (:id, :scope, :item_id, "
                    ":item_number, :label, :kind, :start_on, :duration_days, :day_type, :calendar, "
                    ":due_on, :warn_days_json, :owner, :clause_id, :state, 0, :last_seq)"
                ),
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
                    "due_on": p["due_on"],
                    "warn_days_json": json_text(p.get("warn_days") or []),
                    "owner": p.get("owner"),
                    "clause_id": p.get("clause_id"),
                    "state": CLOCK_RUNNING,
                },
            )
        elif et == CLOCK_PAUSED:
            result = conn.execute(
                text(
                    f"UPDATE {CLOCK_TABLE} SET state = :state, paused_on = :paused_on, "
                    "pause_reason = :pause_reason, last_seq = :last_seq WHERE id = :id"
                ),
                {
                    **base,
                    "state": CLOCK_PAUSED_STATE,
                    "paused_on": p["day"],
                    "pause_reason": p["reason"],
                },
            )
            self._require(result.rowcount, event)
        elif et == CLOCK_RESUMED:
            result = conn.execute(
                text(
                    f"UPDATE {CLOCK_TABLE} SET state = :state, due_on = :due_on, "
                    "paused_on = NULL, pause_reason = NULL, last_seq = :last_seq WHERE id = :id"
                ),
                {**base, "state": CLOCK_RUNNING, "due_on": p["due_on"]},
            )
            self._require(result.rowcount, event)
        elif et == CLOCK_RESTARTED:
            # A restart reopens a clock that was met, cancelled or expired.
            result = conn.execute(
                text(
                    f"UPDATE {CLOCK_TABLE} SET state = :state, start_on = :start_on, "
                    "due_on = :due_on, paused_on = NULL, pause_reason = NULL, closed_on = NULL, "
                    "closed_reason = NULL, warned_level = NULL, restarts = restarts + 1, "
                    "last_seq = :last_seq WHERE id = :id"
                ),
                {
                    **base,
                    "state": CLOCK_RUNNING,
                    "start_on": p["start_on"],
                    "due_on": p["due_on"],
                },
            )
            self._require(result.rowcount, event)
        elif et in (CLOCK_MET, CLOCK_CANCELLED):
            if et == CLOCK_MET:
                state = CLOCK_MET_STATE
                reason = p.get("reason") or p.get("response_id")
            else:
                state = CLOCK_CANCELLED_STATE
                reason = p["reason"]
            result = conn.execute(
                text(
                    f"UPDATE {CLOCK_TABLE} SET state = :state, closed_on = :closed_on, "
                    "closed_reason = :closed_reason, paused_on = NULL, pause_reason = NULL, "
                    "last_seq = :last_seq WHERE id = :id"
                ),
                {
                    **base,
                    "state": state,
                    "closed_on": p["day"],
                    "closed_reason": reason,
                },
            )
            self._require(result.rowcount, event)
        elif et == CLOCK_WARNED:
            result = conn.execute(
                text(
                    f"UPDATE {CLOCK_TABLE} SET warned_level = :level, last_seq = :last_seq "
                    "WHERE id = :id"
                ),
                {**base, "level": p["level"]},
            )
            self._require(result.rowcount, event)
        elif et == CLOCK_EXPIRED:
            result = conn.execute(
                text(
                    f"UPDATE {CLOCK_TABLE} SET state = :state, last_seq = :last_seq WHERE id = :id"
                ),
                {**base, "state": CLOCK_EXPIRED_STATE},
            )
            self._require(result.rowcount, event)
        else:
            raise ValueError(f"ClockProjector cannot apply event type: {et}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CLOCK_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CLOCK_TABLE}"))
