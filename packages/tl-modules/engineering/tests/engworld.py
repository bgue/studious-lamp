"""Shared support of the engineering module tests (the name is unique on purpose: L-P1-I0A-1).

``Events`` builds ledger ``Event`` values the way the ledger would hand them to a projector, so a
projector test needs no unit of work. ``install`` creates every table the default projectors
define (the module's included) on an engine; ``apply`` runs the registered projectors over events;
``rows`` and ``record`` read the tables back as plain dicts.
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
BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
PROJECT = "project:P123"
COMPANY = "company"


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
            actor="user:test",
            recorded_at=at,
            effective_at=at,
            correlation_id="c",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"h{self.seq}",
        )

    def created(
        self,
        stream_id: str,
        record_type: str,
        key: str,
        *,
        title: str = "t",
        scope: str = PROJECT,
    ) -> Event:
        """``Record.Created``: the envelope event every module record starts with."""
        return self.make(
            "Record.Created",
            {"record_type": record_type, "key": key, "title": title, "psets": {}},
            stream_id=stream_id,
            stream_type=record_type,
            scope=scope,
        )


def install(engine: Engine, dialect: str) -> None:
    """Create every table of every default projector."""
    with engine.begin() as conn:
        for projector in default_registry().all():
            for statement in projector.ddl(dialect):
                conn.exec_driver_sql(statement)


def apply(engine: Engine, *events: Event) -> None:
    """Run the registered projectors over ``events`` in one transaction."""
    registry = default_registry()
    with engine.begin() as conn:
        for event in events:
            for projector in registry.for_event(event.event_type):
                projector.apply(conn, event)


def rows(engine: Engine, table: str, order: str = "id") -> list[dict[str, Any]]:
    """Every row of ``table`` (a name from the module, never user input), ordered by ``order``."""
    with engine.connect() as conn:
        found = conn.execute(text(f"SELECT * FROM {table} ORDER BY {order}")).mappings()
        return [dict(r) for r in found]


def record(engine: Engine, record_id: str) -> dict[str, Any]:
    """The ``cur_core_record`` row of ``record_id``."""
    with engine.connect() as conn:
        row = (
            conn.execute(text("SELECT * FROM cur_core_record WHERE id = :id"), {"id": record_id})
            .mappings()
            .one()
        )
        return dict(row)


def as_json(value: Any) -> Any:
    """A JSON column as Python: SQLite and Postgres both hand back JSON text through the adapter."""
    return json.loads(value) if isinstance(value, str) else value


def put_standard(
    events: Events,
    engine: Engine,
    kind: str,
    code: str,
    *,
    label: str | None = None,
    policy: str | None = None,
    data: dict[str, Any] | None = None,
    edition: str = "co.acme.standards@1.0.0",
) -> str:
    """Write a registry entry straight through the projectors (no handler). Returns its id."""
    record_type = {
        "code_list": "engineering.CodeList",
        "mnemonic": "engineering.Mnemonic",
        "numbering_pattern": "engineering.NumberingPattern",
    }[kind]
    stream = f"S-{kind}-{code}-{edition}"
    apply(
        engine,
        events.created(stream, record_type, f"{kind}:{code}@{edition}", scope=COMPANY),
        events.make(
            "Standard.Defined",
            {
                "kind": kind,
                "code": code,
                "label": label or code,
                "edition": edition,
                "value_list_policy": policy,
                "data": data or {},
            },
            stream_id=stream,
            stream_type=record_type,
            scope=COMPANY,
        ),
    )
    return stream


def put_value(
    events: Events,
    engine: Engine,
    code_list: str,
    code: str,
    *,
    scope: str = COMPANY,
    **more: Any,
) -> str:
    """Write a code value straight through the projectors (no handler). Returns its id."""
    stream = f"V-{scope}-{code_list}-{code}"
    payload: dict[str, Any] = {
        "code_list": code_list,
        "code": code,
        "label": f"{code} label",
        "origin": "company" if scope == COMPANY else "project",
        "edition": "co.acme.standards@1.0.0",
    }
    payload.update(more)
    apply(
        engine,
        events.created(stream, "engineering.CodeValue", f"CV:{code_list}.{code}", scope=scope),
        events.make(
            "CodeValue.Defined",
            payload,
            stream_id=stream,
            stream_type="engineering.CodeValue",
            scope=scope,
        ),
    )
    return stream
