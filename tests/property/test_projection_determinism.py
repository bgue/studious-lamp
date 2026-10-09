"""Projection determinism: replaying the ledger twice yields identical rows (P0-I1-T07).

Run with ``pytest tests/property -k projection``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
from tl_core.projection import InMemoryRegistry
from tl_core.projection.testing import CounterProjector


def registry() -> InMemoryRegistry:
    return InMemoryRegistry([CounterProjector()])


def rows(db: Path) -> list[tuple[str, int, int]]:
    with open_uow(db, readonly=True, registry=registry()) as uow:
        found = uow.conn().execute(
            text("SELECT stream_id, n, last_seq FROM cur_test_counter ORDER BY stream_id")
        )
        return [(r.stream_id, r.n, r.last_seq) for r in found]


batches = st.lists(
    st.tuples(st.integers(min_value=0, max_value=4), st.integers(min_value=1, max_value=4)),
    min_size=1,
    max_size=12,
)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(batches=batches)
def test_projection_replay_twice_gives_identical_rows(batches: list[tuple[int, int]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tl.db"
        create_schema(db, registry=registry())
        versions: dict[str, int] = {}
        for stream_no, count in batches:
            stream = f"s{stream_no}"
            with open_uow(db, registry=registry()) as uow:
                uow.append(
                    stream_id=stream,
                    stream_type="test.Thing",
                    scope="project:P1",
                    expected_version=versions.get(stream, 0),
                    events=[
                        NewEvent(event_type="Test.Bumped", payload={"i": i}) for i in range(count)
                    ],
                    actor="user:dev",
                    source="test",
                    correlation_id="c",
                )
            versions[stream] = versions.get(stream, 0) + count
        live = rows(db)
        rebuild_projections(db, registry=registry())
        first = rows(db)
        rebuild_projections(db, registry=registry())
        second = rows(db)
        assert live == first == second
        assert sum(n for _, n, _ in live) == sum(c for _, c in batches)
