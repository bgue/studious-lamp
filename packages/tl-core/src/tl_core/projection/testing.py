"""Test-only projector: counts events per stream in ``test_counter_rows``.

It exists so the projector engine can be tested without a real record type. It is not part of
the schema, is never registered by default, and its table is not a generated ``cur_*`` table.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from tl_core.ledger import Event


class CounterProjector:
    name = "test_counter"
    handles = frozenset({"Test.Bumped"})

    def ddl(self, dialect: str) -> list[str]:
        return [
            "CREATE TABLE IF NOT EXISTS test_counter_rows ("
            "stream_id TEXT PRIMARY KEY, n INTEGER NOT NULL, last_seq INTEGER NOT NULL)"
        ]

    def apply(self, conn: Connection, event: Event) -> None:
        params = {"s": event.stream_id, "q": event.seq}
        updated = conn.execute(
            text("UPDATE test_counter_rows SET n = n + 1, last_seq = :q WHERE stream_id = :s"),
            params,
        )
        if updated.rowcount == 0:
            conn.execute(
                text("INSERT INTO test_counter_rows (stream_id, n, last_seq) VALUES (:s, 1, :q)"),
                params,
            )

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM test_counter_rows"))
