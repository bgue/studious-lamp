"""Helpers of the rebuild bench: a registry that times each projector, and a table fingerprint."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from sqlalchemy import Connection, text
from tl_adapters import db as adapter_db
from tl_core.ledger import Event
from tl_core.projection.defaults import default_registry
from tl_core.projection.registry import InMemoryRegistry
from tl_core.projection.types import Projector

TABLES = (
    "cur_core_record",
    "cur_pset_values",
    "cur_links",
    "cur_link_counts",
    "cur_workflow_state",
    "cur_feed_items",
    "cur_feed_tags",
)


class TimedProjector:
    """Forwards to a projector and adds the seconds ``apply`` and ``reset`` take to ``timings``."""

    def __init__(
        self, inner: Projector, timings: dict[str, float], applies: dict[str, int]
    ) -> None:
        self._inner = inner
        self._timings = timings
        self._applies = applies
        self.name = inner.name
        self.handles = inner.handles
        self.handles_all = bool(getattr(inner, "handles_all", False))

    def ddl(self, dialect: str) -> list[str]:
        return self._inner.ddl(dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        started = time.perf_counter()
        self._inner.apply(conn, event)
        self._timings[self.name] += time.perf_counter() - started
        self._applies[self.name] += 1

    def reset(self, conn: Connection) -> None:
        started = time.perf_counter()
        self._inner.reset(conn)
        self._timings[self.name + " (reset)"] += time.perf_counter() - started


class TimedRegistry(InMemoryRegistry):
    """The default projectors, each wrapped so the time spent in it is recorded by name."""

    def __init__(self) -> None:
        self.timings: dict[str, float] = defaultdict(float)
        self.applies: dict[str, int] = defaultdict(int)
        super().__init__(
            TimedProjector(p, self.timings, self.applies) for p in default_registry().all()
        )


def fingerprint(target: adapter_db.DbTarget) -> dict[str, Any]:
    """Row counts of the projection tables and the highest ``last_seq`` of the record table."""
    engine = adapter_db.make_engine(target)
    try:
        with adapter_db.read_tx(engine) as conn:
            counts = {
                table: int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())  # noqa: S608
                for table in TABLES
            }
            counts["max_last_seq"] = int(
                conn.execute(
                    text("SELECT COALESCE(MAX(last_seq), 0) FROM cur_core_record")
                ).scalar_one()
            )
            counts["sum_version"] = int(
                conn.execute(
                    text("SELECT COALESCE(SUM(version), 0) FROM cur_core_record")
                ).scalar_one()
            )
    finally:
        engine.dispose()
    return counts
