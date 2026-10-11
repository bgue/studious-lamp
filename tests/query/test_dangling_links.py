"""A link counts only when the record at its other end exists (it always did; P0-I8 D13).

The link predicates became sets of ids built from ``cur_links``. A link whose other end has no
``cur_core_record`` row (a ghost) must still be ignored, in both directions, by ``linked``,
``count(linked)`` and ``missing(link)``. The seed's links are written straight into the table, so
the ghosts are too.
"""

from __future__ import annotations

import pytest
from query_seed import SCOPE, record_id
from sqlalchemy import text
from tl_adapters._unit import BaseUnitOfWork
from tl_adapters.db import DbTarget, open_uow
from tl_core.query import QuerySpec, count_query, parse, run_query

QUERIES = [
    "linked",
    "linked(requires)",
    "linked(raised_against)",
    "count(linked)>=1",
    "count(linked)=0",
    "count(linked)>1",
    "missing(link)",
    "missing(link(requires))",
]


def keys(uow: BaseUnitOfWork, query: str) -> list[str]:
    spec = QuerySpec(scope=SCOPE, where=parse(query), order_by=[("key", "asc")])
    rows = run_query(uow, spec)
    assert count_query(uow, spec) == len(rows)
    return [str(r["key"]) for r in rows]


def add_ghost_links(db: DbTarget) -> None:
    sql = text(
        "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, source, "
        "created_by, created_at, updated_at, version, last_seq) VALUES (:l, :scope, :f, :t, :r, "
        "'active', 'manual', 'user:t', '2026-10-01T00:00:00+00:00', "
        "'2026-10-01T00:00:00+00:00', 1, 1)"
    )
    with open_uow(db) as uow:
        for link_id, source, target, relation in (
            ("GHOST-OUT", record_id("W-003"), "01GHOSTRECORDNOTINTHETABLE", "requires"),
            ("GHOST-IN", "01GHOSTRECORDNOTINTHETABLE", record_id("PRM-001"), "requires"),
            ("GHOST-NCR", record_id("V-0001"), "01GHOSTRECORDNOTINTHETABLE", "raised_against"),
        ):
            uow.conn().execute(
                sql, {"l": link_id, "scope": SCOPE, "f": source, "t": target, "r": relation}
            )


@pytest.mark.parametrize("query", QUERIES)
def test_a_link_to_a_record_that_does_not_exist_changes_no_result(db: DbTarget, query: str) -> None:
    with open_uow(db, readonly=True) as uow:
        before = keys(uow, query)
    add_ghost_links(db)
    with open_uow(db, readonly=True) as uow:
        after = keys(uow, query)
    assert after == before


def test_the_seed_still_answers_what_it_did(db: DbTarget) -> None:
    add_ghost_links(db)
    with open_uow(db, readonly=True) as uow:
        assert "V-0001" not in keys(uow, "linked")  # its only link is to a ghost
        assert "V-0001" in keys(uow, "missing(link)")
        assert "W-003" in keys(uow, "missing(link)")
