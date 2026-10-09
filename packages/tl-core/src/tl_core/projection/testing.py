"""A tiny projector for tests: counts events per stream in ``cur_test_counter``."""

from __future__ import annotations

from sqlalchemy import Connection, text

from tl_core.ledger import Event


class CounterProjector:
    name = "test_counter"
    handles = frozenset({"Test.Bumped"})

    def ddl(self, dialect: str) -> list[str]:
        return [
            "CREATE TABLE IF NOT EXISTS cur_test_counter ("
            "stream_id TEXT PRIMARY KEY, n INTEGER NOT NULL, last_seq INTEGER NOT NULL)"
        ]

    def apply(self, conn: Connection, event: Event) -> None:
        conn.execute(
            text(
                "INSERT INTO cur_test_counter (stream_id, n, last_seq) VALUES (:s, 1, :q) "
                "ON CONFLICT(stream_id) DO UPDATE SET n = n + 1, last_seq = :q"
            ),
            {"s": event.stream_id, "q": event.seq},
        )

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_test_counter"))
