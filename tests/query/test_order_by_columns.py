"""Ordering by the NOT NULL columns (P0-I8 D13): created_at, updated_at and version, id as tiebreak.

Their ORDER BY has no "empty sorts last" term any more (so an index can serve it). The order must
not change: ties break by ``id`` ascending in both directions, on both adapters, through
``run_query`` and through ``list_records``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.ledger import NewEvent
from tl_core.query import QuerySpec, run_query
from tl_core.services.queries import list_records

Direction = Literal["asc", "desc"]
SCOPE = "project:p1"
# id: (created_at, updated_at, version); ties on every column but id
ROWS = {
    "r1": ("2026-01-02T00:00:00.000000+00:00", "2026-01-05T00:00:00.000000+00:00", 2),
    "r2": ("2026-01-01T00:00:00.000000+00:00", "2026-01-05T00:00:00.000000+00:00", 1),
    "r3": ("2026-01-02T00:00:00.000000+00:00", "2026-01-04T00:00:00.000000+00:00", 2),
    "r4": ("2026-01-03T00:00:00.000000+00:00", "2026-01-04T00:00:00.000000+00:00", 3),
}


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    with open_uow(target) as uow:
        for record_id, (created, updated, version) in ROWS.items():
            uow.append(
                stream_id=record_id,
                stream_type="core.Record",
                scope=SCOPE,
                expected_version=0,
                events=[
                    NewEvent(
                        event_type="Record.Created",
                        payload={
                            "record_type": "core.Record",
                            "key": record_id.upper(),
                            "title": record_id,
                            "psets": {},
                        },
                    )
                ],
                actor="user:t",
                source="test",
                correlation_id="c",
            )
            uow.conn().execute(
                text(
                    "UPDATE cur_core_record SET created_at = :c, updated_at = :u, version = :v "
                    "WHERE id = :id"
                ),
                {"c": created, "u": updated, "v": version, "id": record_id},
            )
    return target


EXPECTED: dict[tuple[str, Direction], list[str]] = {
    ("created_at", "asc"): ["r2", "r1", "r3", "r4"],
    ("created_at", "desc"): ["r4", "r1", "r3", "r2"],
    ("updated_at", "asc"): ["r3", "r4", "r1", "r2"],
    ("updated_at", "desc"): ["r1", "r2", "r3", "r4"],
    ("version", "asc"): ["r2", "r1", "r3", "r4"],
    ("version", "desc"): ["r4", "r1", "r3", "r2"],
}


@pytest.mark.parametrize(("column", "direction"), list(EXPECTED))
def test_both_query_paths_order_by_the_column_and_break_ties_by_id(
    db: DbTarget, column: str, direction: Direction
) -> None:
    order: list[tuple[str, Direction]] = [(column, direction)]
    with open_uow(db, readonly=True) as uow:
        compiled = run_query(uow, QuerySpec(scope=SCOPE, order_by=order))
        listed = list_records(uow, SCOPE, order_by=order)
    assert [r["id"] for r in compiled] == EXPECTED[(column, direction)]
    assert [r["id"] for r in listed] == EXPECTED[(column, direction)]
