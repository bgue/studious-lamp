"""SQLite admin operations that bypass the ledger: restore from an archive."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Connection
from tl_core.ledger import Event

from tl_adapters._restore import insert_events
from tl_adapters.sqlite.engine import is_write_connection


def restore_events(conn: Connection, events: Iterable[Event]) -> int:
    """Insert archived ``events`` verbatim into an empty ``events`` table; return how many.

    ``conn`` comes from ``sqlite.engine.write_tx`` and the table must already exist and be empty
    (``RestoreError`` otherwise). Events keep their seq, ids, times and hashes; nothing is
    recomputed. The caller rebuilds projections afterwards.
    """
    if not is_write_connection(conn):
        raise RuntimeError("restore_events needs a connection from write_tx")
    return insert_events(conn, events)
