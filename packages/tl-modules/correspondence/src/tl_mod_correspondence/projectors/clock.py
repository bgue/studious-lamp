# ruff: noqa: F401, F841
"""ClockProjector: the ``ResponseClock.*`` events into ``cur_correspondence_response_clock``.

The projector does no arithmetic. ``Started``, ``Resumed`` and ``Restarted`` carry the due date the
clock engine computed (``tl_mod_correspondence.clocks``); the row copies it. ``Paused`` records the
pause, ``Met`` and ``Cancelled`` close the clock, ``Warned`` records the warning threshold crossed
and ``Expired`` marks a running clock past its date. Deterministic. Register it after
``RecordProjector``.

STUB (P1-I5-T03b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
        # STEPS
        # 1. `p = event.payload`, `et = event.event_type`, `base = {"id": event.stream_id,
        #    "last_seq": event.seq}`. Named parameters, table name from the constant CLOCK_TABLE.
        #    The projector does no date arithmetic: due dates come from the events.
        # 2. CLOCK_STARTED: INSERT into CLOCK_TABLE: id, scope (`event.scope`), item_id,
        #    item_number, label, kind, start_on, duration_days, day_type, calendar, due_on (all
        #    required keys), `warn_days_json` = `json_text(p.get("warn_days") or [])`, owner and
        #    clause_id (`p.get`), state 'running', restarts 0, last_seq.
        # 3. CLOCK_PAUSED: UPDATE state 'paused', paused_on = `p["day"]`, pause_reason =
        #    `p["reason"]`, last_seq.
        # 4. CLOCK_RESUMED: UPDATE state 'running', due_on = `p["due_on"]`, paused_on NULL,
        #    pause_reason NULL, last_seq.
        # 5. CLOCK_RESTARTED: UPDATE state 'running', start_on = `p["start_on"]`, due_on =
        #    `p["due_on"]`, paused_on NULL, pause_reason NULL, closed_on NULL, closed_reason NULL,
        #    warned_level NULL, restarts = restarts + 1, last_seq. (A restart reopens a clock that
        #    was met, cancelled or expired.)
        # 6. CLOCK_MET: UPDATE state 'met', closed_on = `p["day"]`, closed_reason = `p.get("reason")
        #    or p.get("response_id")`, paused_on NULL, pause_reason NULL, last_seq.
        # 7. CLOCK_CANCELLED: UPDATE state 'cancelled', closed_on = `p["day"]`, closed_reason =
        #    `p["reason"]`, paused_on NULL, pause_reason NULL, last_seq. (Use one shared statement
        #    with a `:state` parameter for met and cancelled if you like.)
        # 8. CLOCK_WARNED: UPDATE warned_level = `p["level"]` and last_seq.
        # 9. CLOCK_EXPIRED: UPDATE state 'expired' and last_seq (the due date and closed_on stay).
        # 10. Any other event type: `raise ValueError(f"ClockProjector cannot apply event type:
        #    {et}")`. Every UPDATE branch checks its row count with `self._require(rowcount,
        #    event)`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CLOCK_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` the CLOCK_TABLE.
        raise NotImplementedError
