"""ThreadProjector: the ``CorrespondenceThread.*`` events into the thread table.

``Defined`` inserts the thread with its first item; ``ItemAdded`` counts another item and moves
``last_item_on`` forward (never back); ``StateChanged`` opens or closes it. Deterministic.
Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    THREAD_DEFINED,
    THREAD_ITEM_ADDED,
    THREAD_OPEN,
    THREAD_STATE_CHANGED,
    THREAD_TABLE,
    THREAD_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, touch_record


class ThreadProjector:
    name = "correspondence_thread"
    handles = frozenset({THREAD_DEFINED, THREAD_ITEM_ADDED, THREAD_STATE_CHANGED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(THREAD_TABLE, dialect) + ddl_for(THREAD_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        base = {"id": event.stream_id, "last_seq": event.seq}
        if event.event_type == THREAD_DEFINED:
            conn.execute(
                text(
                    f"INSERT INTO {THREAD_TABLE} (id, scope, number, subject_key, domain, state, "
                    "governing_item_id, item_count, last_item_on, last_seq) VALUES (:id, :scope, "
                    ":number, :subject_key, :domain, :state, :governing_item_id, 1, "
                    ":last_item_on, :last_seq)"
                ),
                {
                    **base,
                    "scope": event.scope,
                    "number": payload["number"],
                    "subject_key": payload["subject_key"],
                    "domain": payload.get("domain"),
                    "state": THREAD_OPEN,
                    "governing_item_id": payload["governing_item_id"],
                    "last_item_on": payload.get("item_on"),
                },
            )
        elif event.event_type == THREAD_ITEM_ADDED:
            found = conn.execute(
                text(f"SELECT last_item_on FROM {THREAD_TABLE} WHERE id = :id"),
                {"id": event.stream_id},
            ).first()
            if found is None:
                raise LookupError(f"no {THREAD_TABLE} row for stream {event.stream_id}")
            current: str | None = found[0]
            item_on = payload.get("item_on")
            if item_on is not None and (current is None or item_on > current):
                last_item_on = item_on
            else:
                last_item_on = current
            conn.execute(
                text(
                    f"UPDATE {THREAD_TABLE} SET item_count = item_count + 1, "
                    "last_item_on = :last_item_on, last_seq = :last_seq WHERE id = :id"
                ),
                {**base, "last_item_on": last_item_on},
            )
        elif event.event_type == THREAD_STATE_CHANGED:
            result = conn.execute(
                text(
                    f"UPDATE {THREAD_TABLE} SET state = :state, last_seq = :last_seq WHERE id = :id"
                ),
                {**base, "state": payload["state"]},
            )
            self._require(result.rowcount, event)
        else:
            raise ValueError(f"ThreadProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {THREAD_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {THREAD_TABLE}"))
