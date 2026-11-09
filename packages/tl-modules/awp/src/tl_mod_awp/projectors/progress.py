"""Projector of IWP progress: ``cur_awp_iwp_progress``.

``IWP.ProgressRecorded`` replaces the row of its IWP (the event holds the whole figure).
``IWP.Started`` and ``IWP.FieldCompleted`` change no column: they move the envelope's version and
the IWP row's ``last_seq``, as the scope and hold events do in ``iwp.py``. No handler yet: the
commands come in P2-I5 S2. Deterministic: the rows depend only on the events, and a rebuild never
calls the engine. ``as_of_seq`` is the ``seq`` of the event.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_awp.names import (
    IWP_FIELD_COMPLETED,
    IWP_PROGRESS_RECORDED,
    IWP_PROGRESS_TABLE,
    IWP_STARTED,
    IWP_TABLE,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_CLEAR_SQL = text(f"DELETE FROM {IWP_PROGRESS_TABLE} WHERE iwp_id = :iwp_id")
_INSERT_SQL = text(
    f"INSERT INTO {IWP_PROGRESS_TABLE} (iwp_id, scope, earned_pct, edition, as_of_seq, last_seq) "
    "VALUES (:iwp_id, :scope, :earned_pct, :edition, :as_of_seq, :last_seq)"
)
_BUMP_SQL = text(f"UPDATE {IWP_TABLE} SET last_seq = :last_seq WHERE id = :id")


class ProgressProjector:
    name = "awp_progress"
    handles = frozenset({IWP_PROGRESS_RECORDED, IWP_STARTED, IWP_FIELD_COMPLETED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(IWP_PROGRESS_TABLE, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == IWP_PROGRESS_RECORDED:
            iwp_id = payload["iwp_id"]
            conn.execute(_CLEAR_SQL, {"iwp_id": iwp_id})
            conn.execute(
                _INSERT_SQL,
                {
                    "iwp_id": iwp_id,
                    "scope": event.scope,
                    "earned_pct": payload["earned_pct"],
                    "edition": payload["edition"],
                    "as_of_seq": event.seq,
                    "last_seq": event.seq,
                },
            )
        elif kind in (IWP_STARTED, IWP_FIELD_COMPLETED):
            conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        else:
            raise ValueError(f"ProgressProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {IWP_PROGRESS_TABLE}"))


def progress_projectors() -> list[ProgressProjector]:
    """Fresh projectors of the progress table."""
    return [ProgressProjector()]
