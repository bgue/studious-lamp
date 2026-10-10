"""PostgresUowFactory: one pooled engine, many units of work, same behaviour as open_uow (P0-I5)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from tl_adapters.db import create_schema
from tl_adapters.postgres.factory import PostgresUowFactory
from tl_core.bus import InProcessBus
from tl_core.ledger import Event, NewEvent

pytestmark = pytest.mark.requires_postgres


def bump(uow: object, stream: str, expected: int = 0) -> None:
    uow.append(  # type: ignore[attr-defined]
        stream_id=stream,
        stream_type="core.Record",
        scope="project:P1",
        expected_version=expected,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={"record_type": "core.Record", "key": stream, "title": stream, "psets": {}},
            )
        ],
        actor="user:t",
        source="test",
        correlation_id="c",
    )


def test_the_factory_runs_projectors_and_publishes_in_commit_order(pg_db: str) -> None:
    create_schema(pg_db)
    bus = InProcessBus()
    seen: list[Event] = []
    bus.subscribe(seen.append)
    factory = PostgresUowFactory(pg_db, bus=bus)
    try:
        for n in range(3):
            with factory() as uow:
                bump(uow, f"R{n}")
        with factory(readonly=True) as uow:
            titles = [
                r.title
                for r in uow.conn().execute(
                    text("SELECT title FROM cur_core_record ORDER BY title")
                )
            ]
            assert uow.ledger.head_seq() == 3
            with pytest.raises(RuntimeError, match="read-only"):
                bump(uow, "nope")
    finally:
        factory.dispose()
    assert titles == ["R0", "R1", "R2"]
    assert [e.seq for e in seen] == [1, 2, 3]


def test_a_failed_transaction_leaves_nothing_and_the_pool_keeps_working(pg_db: str) -> None:
    create_schema(pg_db)
    factory = PostgresUowFactory(pg_db)
    try:
        with pytest.raises(RuntimeError, match="abort"), factory() as uow:
            bump(uow, "R0")
            raise RuntimeError("abort")
        with factory() as uow:
            bump(uow, "R0")
        with factory(readonly=True) as uow:
            assert uow.ledger.head_seq() == 1
    finally:
        factory.dispose()
