"""LinkProjector round trips (P0-I8 D13): one upsert per record end for the link counts.

A link event refreshed the counts of both its records with four statements each (read the counts,
read the record's scope, update, insert when absent). One ``INSERT ... SELECT ... ON CONFLICT DO
UPDATE`` per end does the same. These tests pin the budget and the rows; the behaviour tests stay
in ``test_link_projector.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, event, text
from tl_core.ledger import Event
from tl_core.projection.defaults import default_registry
from tl_core.projection.links import LinkProjector

AT = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
A, B, C = "REC-A", "REC-B", "REC-C"


def make(
    seq: int,
    event_type: str,
    payload: dict[str, Any],
    stream_id: str,
    *,
    version: int = 1,
    scope: str = "project:P123",
    stream_type: str = "core.Link",
) -> Event:
    return Event(
        event_type=event_type,
        payload=payload,
        seq=seq,
        event_id=f"E{seq:06d}",
        stream_id=stream_id,
        stream_type=stream_type,
        stream_version=version,
        scope=scope,
        actor="user:test",
        recorded_at=AT,
        effective_at=AT,
        correlation_id="c",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash=f"h{seq}",
    )


def record(seq: int, record_id: str, scope: str = "project:P123") -> Event:
    payload = {"record_type": "core.Record", "key": f"K-{record_id}", "title": record_id}
    return make(seq, "Record.Created", payload, record_id, scope=scope, stream_type="core.Record")


def added(seq: int, link_id: str, from_id: str, to_id: str, scope: str = "project:P123") -> Event:
    payload = {
        "link_id": link_id,
        "from_ref": from_id,
        "to_ref": to_id,
        "relation": "references",
        "pin": None,
        "source": "manual",
        "note": None,
    }
    return make(seq, "Link.Added", payload, link_id, scope=scope)


@pytest.fixture
def engine(new_engine: Callable[[], Engine], dialect: str) -> Iterator[Engine]:
    eng = new_engine()
    with eng.begin() as conn:
        for projector in default_registry().all():
            for statement in projector.ddl(dialect):
                conn.exec_driver_sql(statement)
    yield eng
    eng.dispose()


def count_statements(conn: Connection, run: Callable[[], None]) -> list[str]:
    seen: list[str] = []

    def listener(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
        seen.append(statement)

    event.listen(conn.engine, "before_cursor_execute", listener)
    try:
        run()
    finally:
        event.remove(conn.engine, "before_cursor_execute", listener)
    return seen


def counts(conn: Connection, record_id: str) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT * FROM cur_link_counts WHERE record_id = :id"), {"id": record_id}
    ).mappings()
    found = row.first()
    assert found is not None, f"no counts row for {record_id}"
    return dict(found)


def apply_all(conn: Connection, *events: Event) -> None:
    registry = default_registry()
    for item in events:
        for projector in registry.for_event(item.event_type):
            projector.apply(conn, item)


def test_a_new_link_costs_three_statements_for_a_new_pair_of_ends(engine: Engine) -> None:
    link = added(3, "L-1", A, B)
    with engine.begin() as conn:
        apply_all(conn, record(1, A), record(2, B))
        statements = count_statements(conn, lambda: LinkProjector().apply(conn, link))
        a, b = counts(conn, A), counts(conn, B)
    assert len(statements) <= 3, statements  # the link row and one upsert per end
    assert (a["active_out"], a["active_in"], a["last_seq"]) == (1, 0, 3)
    assert (b["active_out"], b["active_in"], b["last_seq"]) == (0, 1, 3)
    assert a["scope"] == b["scope"] == "project:P123"


def test_a_second_link_updates_the_existing_counts_rows(engine: Engine) -> None:
    with engine.begin() as conn:
        apply_all(conn, record(1, A), record(2, B), record(3, C), added(4, "L-1", A, B))
        second = added(5, "L-2", C, A)
        statements = count_statements(conn, lambda: LinkProjector().apply(conn, second))
        a, b, c = counts(conn, A), counts(conn, B), counts(conn, C)
    assert len(statements) <= 3, statements
    assert (a["active_out"], a["active_in"], a["last_seq"]) == (1, 1, 5)
    assert (b["active_out"], b["active_in"], b["last_seq"]) == (0, 1, 4)  # not touched
    assert (c["active_out"], c["active_in"], c["last_seq"]) == (1, 0, 5)


def test_a_change_to_a_link_costs_four_statements(engine: Engine) -> None:
    with engine.begin() as conn:
        apply_all(conn, record(1, A), record(2, B), added(3, "L-1", A, B))
        flag = make(
            4, "Link.Flagged", {"link_id": "L-1", "status": "stale", "reason": "moved"}, "L-1"
        )
        flag = flag.model_copy(update={"stream_version": 2})
        statements = count_statements(conn, lambda: LinkProjector().apply(conn, flag))
        a, b = counts(conn, A), counts(conn, B)
    assert len(statements) <= 4, statements  # read the link, update it, one upsert per end
    assert (a["active_out"], a["stale"], a["last_seq"]) == (0, 1, 4)
    assert (b["active_in"], b["stale"], b["last_seq"]) == (0, 1, 4)


def test_the_scope_of_the_counts_row_is_the_records_not_the_links(engine: Engine) -> None:
    link = added(3, "L-1", A, B, scope="project:P999")
    with engine.begin() as conn:
        apply_all(conn, record(1, A, "project:P123"), record(2, B, "company"), link)
        a, b = counts(conn, A), counts(conn, B)
    assert a["scope"] == "project:P123" and b["scope"] == "company"


def test_a_record_that_does_not_exist_yet_takes_the_scope_of_the_event(engine: Engine) -> None:
    link = added(1, "L-1", "REC-X", "REC-Y", scope="project:P123")
    with engine.begin() as conn:
        apply_all(conn, link)
        assert counts(conn, "REC-X")["scope"] == "project:P123"
        assert counts(conn, "REC-Y")["active_in"] == 1
