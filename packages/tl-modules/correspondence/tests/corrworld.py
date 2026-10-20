"""Shared support of the correspondence module tests (the name is unique on purpose: L-P1-I0A-1).

``install`` creates every table of every default projector on an engine; ``Events`` builds ledger
events for projector tests; ``apply`` and ``table_rows`` run the projectors and read a table back.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from tl_core.ledger import Event
from tl_core.projection.defaults import default_registry

FIXTURES = Path(__file__).resolve().parents[4] / "schema" / "fixtures"
PROJECT = "project:P123"
BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def install(engine: Engine, dialect: str) -> None:
    """Create every table (and view) of every default projector."""
    with engine.begin() as conn:
        for projector in default_registry().all():
            for statement in projector.ddl(dialect):
                conn.exec_driver_sql(statement)


class Events:
    """Numbers events in one global sequence and per-stream versions, like the ledger."""

    def __init__(self) -> None:
        self.seq = 0
        self.versions: dict[str, int] = {}

    def make(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        stream_id: str,
        stream_type: str,
        scope: str = PROJECT,
        actor: str = "user:test",
    ) -> Event:
        self.seq += 1
        version = self.versions.get(stream_id, 0) + 1
        self.versions[stream_id] = version
        at = BASE_TIME + timedelta(minutes=self.seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=self.seq,
            event_id=f"E{self.seq:06d}",
            stream_id=stream_id,
            stream_type=stream_type,
            stream_version=version,
            scope=scope,
            actor=actor,
            recorded_at=at,
            effective_at=at,
            correlation_id="c",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"h{self.seq}",
        )

    def created(
        self, stream_id: str, record_type: str, key: str, *, title: str = "t", scope: str = PROJECT
    ) -> Event:
        """``Record.Created``: the envelope event every module record starts with."""
        return self.make(
            "Record.Created",
            {"record_type": record_type, "key": key, "title": title, "psets": {}},
            stream_id=stream_id,
            stream_type=record_type,
            scope=scope,
        )


def apply(engine: Engine, *events: Event) -> None:
    """Run the registered projectors over ``events`` in one transaction."""
    registry_ = default_registry()
    with engine.begin() as conn:
        for event in events:
            for projector in registry_.for_event(event.event_type):
                projector.apply(conn, event)


def table_rows(engine: Engine, table: str, order: str = "id") -> list[dict[str, Any]]:
    """Every row of ``table`` (a name from the module, never user input), ordered by ``order``."""
    with engine.connect() as conn:
        found = conn.execute(text(f"SELECT * FROM {table} ORDER BY {order}")).mappings()
        return [dict(r) for r in found]


def as_json(value: Any) -> Any:
    """A JSON column as Python: SQLite and Postgres both hand back JSON text through the adapter."""
    return json.loads(value) if isinstance(value, str) else value


__all__ = ["FIXTURES", "PROJECT", "Events", "apply", "as_json", "install", "table_rows"]
