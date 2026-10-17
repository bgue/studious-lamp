# ruff: noqa: F401, F841
"""ThreadProjector: the ``CorrespondenceThread.*`` events into the thread table.

``Defined`` inserts the thread with its first item; ``ItemAdded`` counts another item and moves
``last_item_on`` forward (never back); ``StateChanged`` opens or closes it. Deterministic.
Register it after ``RecordProjector``.

STUB (P1-I5-T03b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    THREAD_DEFINED,
    THREAD_ITEM_ADDED,
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
        # STEPS
        # 1. `payload = event.payload`; `base = {"id": event.stream_id, "last_seq": event.seq}`.
        #    Named parameters, table name from the constant THREAD_TABLE.
        # 2. THREAD_DEFINED: INSERT into THREAD_TABLE: id, scope (`event.scope`), number,
        #    subject_key (required keys), domain (`payload.get`), state 'open', governing_item_id =
        #    `payload["governing_item_id"]`, item_count 1, last_item_on = `payload.get("item_on")`,
        #    last_seq.
        # 3. THREAD_ITEM_ADDED: SELECT last_item_on FROM THREAD_TABLE WHERE id = :id; no row means
        #    `raise LookupError(f"no {THREAD_TABLE} row for stream {event.stream_id}")`. Choose the
        #    newest date in Python: `item_on = payload.get("item_on")`; the new value is `item_on`
        #    when it is not None and (the current value is None or `item_on` is later: ISO dates
        #    compare as strings), else the current value. Postgres cannot infer the type of a bare
        #    parameter in a CASE expression, so do not do this in SQL. Then UPDATE item_count =
        #    item_count + 1, last_item_on = the chosen value, last_seq.
        # 4. THREAD_STATE_CHANGED: UPDATE state = `payload["state"]` and last_seq; check the row
        #    count with `self._require`.
        # 5. Any other event type: `raise ValueError(f"ThreadProjector cannot apply event type:
        #    {event.event_type}")`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {THREAD_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` the THREAD_TABLE.
        raise NotImplementedError
