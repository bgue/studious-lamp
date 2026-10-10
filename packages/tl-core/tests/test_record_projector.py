"""RecordProjector: Record.* events into cur_core_record (P0-I1-T08)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from tl_core.ledger import Event, iso_utc
from tl_core.projection.defaults import default_registry
from tl_core.projection.record import RecordProjector

PROJECTOR = RecordProjector()
BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


class EventFactory:
    """Hand-built events: seq and stream_version count up; recorded_at differs per event."""

    def __init__(self) -> None:
        self._seq = 0
        self._versions: dict[str, int] = {}

    def make(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        stream_id: str = "rec-1",
        scope: str = "project:p1",
    ) -> Event:
        self._seq += 1
        version = self._versions.get(stream_id, 0) + 1
        self._versions[stream_id] = version
        recorded_at = BASE_TIME + timedelta(minutes=self._seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=self._seq,
            event_id=f"EVT{self._seq:06d}",
            stream_id=stream_id,
            stream_type="record",
            stream_version=version,
            scope=scope,
            actor="user:test",
            recorded_at=recorded_at,
            effective_at=recorded_at,
            correlation_id="corr-1",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"hash-{self._seq}",
        )


def created_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "record_type": "rfi",
        "key": "RFI-001",
        "title": "Slab level query",
        "description": "Grid B3 level",
        "psets": {"b": 2, "a": 1},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def engine(new_engine: Callable[[], Engine], dialect: str) -> Iterator[Engine]:
    eng = new_engine()
    with eng.begin() as conn:
        for stmt in PROJECTOR.ddl(dialect):
            conn.execute(text(stmt))
    yield eng
    eng.dispose()


def apply_all(engine: Engine, *events: Event) -> None:
    for event in events:
        with engine.begin() as conn:
            PROJECTOR.apply(conn, event)


def fetch_row(engine: Engine, record_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = (
            conn.execute(text("SELECT * FROM cur_core_record WHERE id = :id"), {"id": record_id})
            .mappings()
            .one()
        )
    return dict(row)


def fetch_all(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM cur_core_record ORDER BY id")).mappings().all()
    return [dict(row) for row in rows]


def test_ddl_creates_table_and_is_idempotent(
    new_engine: Callable[[], Engine], dialect: str
) -> None:
    eng = new_engine()
    statements = PROJECTOR.ddl(dialect)
    assert statements
    with eng.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    with eng.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        names = [n for n in inspect(conn).get_table_names() if n == "cur_core_record"]
    assert len(names) == 1
    eng.dispose()


def test_ddl_postgres_uses_jsonb() -> None:
    statements = PROJECTOR.ddl("postgres")
    assert statements
    assert "JSONB" in "\n".join(statements)


def test_ddl_unknown_dialect_raises() -> None:
    with pytest.raises(ValueError):
        PROJECTOR.ddl("mysql")


def test_created_stores_every_column(new_engine: Callable[[], Engine], dialect: str) -> None:
    eng = new_engine()
    with eng.begin() as conn:
        for stmt in PROJECTOR.ddl(dialect):
            conn.execute(text(stmt))
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload(), stream_id="rec-1")
    apply_all(eng, created)

    row = fetch_row(eng, "rec-1")
    assert row["id"] == "rec-1"
    assert row["key"] == "RFI-001"
    assert row["type"] == "rfi"
    assert row["scope"] == "project:p1"
    assert row["title"] == "Slab level query"
    assert row["description"] == "Grid B3 level"
    assert row["status"] is None
    assert row["psets_json"] == '{"a":1,"b":2}'
    assert row["voided"] == 0
    assert row["version"] == 1
    assert row["last_seq"] == created.seq
    assert row["effective_schema_hash"] is None
    assert row["conformance"] == "ok"
    assert row["created_at"] == iso_utc(created.recorded_at)
    assert row["created_at"] == row["updated_at"]
    eng.dispose()


def test_created_without_optional_fields_uses_defaults(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make(
        "Record.Created",
        {"record_type": "note", "key": None, "title": "Bare"},
        stream_id="rec-bare",
    )
    apply_all(engine, created)

    row = fetch_row(engine, "rec-bare")
    assert row["key"] is None
    assert row["description"] is None
    assert row["psets_json"] == "{}"


def test_updated_changes_title_description_and_psets(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload())
    updated = factory.make(
        "Record.Updated",
        {
            "changes": {
                "title": ["Slab level query", "Slab level RFI"],
                "description": ["Grid B3 level", "Grid B3 top of slab"],
                "psets": [{"b": 2, "a": 1}, {"z": 9, "c": 3}],
            }
        },
    )
    apply_all(engine, created, updated)

    row = fetch_row(engine, "rec-1")
    assert row["title"] == "Slab level RFI"
    assert row["description"] == "Grid B3 top of slab"
    assert row["psets_json"] == '{"c":3,"z":9}'
    assert row["version"] == 2
    assert row["last_seq"] == updated.seq
    assert row["updated_at"] == iso_utc(updated.recorded_at)
    assert row["created_at"] == iso_utc(created.recorded_at)
    assert row["created_at"] != row["updated_at"]


def test_updated_can_change_status_and_key(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload())
    updated = factory.make(
        "Record.Updated",
        {"changes": {"status": [None, "open"], "key": ["RFI-001", "RFI-002"]}},
    )
    apply_all(engine, created, updated)

    row = fetch_row(engine, "rec-1")
    assert row["status"] == "open"
    assert row["key"] == "RFI-002"


def test_corrected_applies_changes_like_updated(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload())
    corrected = factory.make(
        "Record.Corrected",
        {
            "changes": {
                "title": ["Slab level query", "Slab level query (fixed)"],
                "psets": [{"b": 2, "a": 1}, {"y": 1}],
            },
            "reason": "typo in title",
        },
    )
    apply_all(engine, created, corrected)

    row = fetch_row(engine, "rec-1")
    assert row["title"] == "Slab level query (fixed)"
    assert row["description"] == "Grid B3 level"
    assert row["psets_json"] == '{"y":1}'
    assert row["version"] == 2
    assert row["last_seq"] == corrected.seq
    assert row["updated_at"] == iso_utc(corrected.recorded_at)


def test_voided_sets_flag_keeps_row_and_later_update_applies(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload())
    voided = factory.make("Record.Voided", {"reason": "duplicate of RFI-000"})
    apply_all(engine, created, voided)

    row = fetch_row(engine, "rec-1")
    assert row["voided"] == 1
    assert row["version"] == 2
    assert row["last_seq"] == voided.seq
    assert row["updated_at"] == iso_utc(voided.recorded_at)
    assert len(fetch_all(engine)) == 1

    later = factory.make("Record.Updated", {"changes": {"title": ["Slab level query", "Audit"]}})
    apply_all(engine, later)

    row = fetch_row(engine, "rec-1")
    assert row["title"] == "Audit"
    assert row["voided"] == 1
    assert row["version"] == 3
    assert len(fetch_all(engine)) == 1


def test_updated_for_unknown_stream_raises_lookup_error(engine: Engine) -> None:
    factory = EventFactory()
    orphan = factory.make("Record.Updated", {"changes": {"title": ["a", "b"]}}, stream_id="missing")
    with pytest.raises(LookupError):
        apply_all(engine, orphan)


@pytest.mark.parametrize(
    "event_type,payload",
    [
        ("Record.Corrected", {"changes": {"title": ["a", "b"]}, "reason": "x"}),
        ("Record.Voided", {"reason": "x"}),
    ],
)
def test_other_events_for_unknown_stream_raise_lookup_error(
    engine: Engine, event_type: str, payload: dict[str, Any]
) -> None:
    factory = EventFactory()
    orphan = factory.make(event_type, payload, stream_id="missing")
    with pytest.raises(LookupError):
        apply_all(engine, orphan)


def test_unsupported_changes_field_raises_value_error_and_writes_nothing(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload())
    bad = factory.make(
        "Record.Updated",
        {"changes": {"title": ["Slab level query", "Changed"], "bogus": [1, 2]}},
    )
    apply_all(engine, created)
    with pytest.raises(ValueError, match="unsupported field in changes: bogus"):
        apply_all(engine, bad)

    assert fetch_row(engine, "rec-1")["title"] == "Slab level query"


def test_unsupported_event_type_raises_value_error(engine: Engine) -> None:
    factory = EventFactory()
    created = factory.make("Record.Created", created_payload())
    alien = factory.make("Record.Teleported", {})
    apply_all(engine, created)
    with pytest.raises(ValueError):
        apply_all(engine, alien)


def test_same_key_in_same_scope_raises_integrity_error(engine: Engine) -> None:
    factory = EventFactory()
    first = factory.make("Record.Created", created_payload(), stream_id="rec-1")
    second = factory.make("Record.Created", created_payload(), stream_id="rec-2")
    apply_all(engine, first)
    with pytest.raises(IntegrityError):
        apply_all(engine, second)


def test_same_key_in_another_scope_succeeds(engine: Engine) -> None:
    factory = EventFactory()
    first = factory.make("Record.Created", created_payload(), stream_id="rec-1", scope="project:p1")
    second = factory.make(
        "Record.Created", created_payload(), stream_id="rec-2", scope="project:p2"
    )
    apply_all(engine, first, second)

    assert fetch_row(engine, "rec-1")["scope"] == "project:p1"
    assert fetch_row(engine, "rec-2")["scope"] == "project:p2"


def test_reset_empties_table_and_replay_reproduces_rows(engine: Engine) -> None:
    factory = EventFactory()
    events = [
        factory.make("Record.Created", created_payload(), stream_id="rec-1"),
        factory.make(
            "Record.Created",
            created_payload(key="RFI-002", title="Second"),
            stream_id="rec-2",
        ),
        factory.make("Record.Updated", {"changes": {"status": [None, "open"]}}, stream_id="rec-1"),
        factory.make("Record.Corrected", {"changes": {"title": ["x", "Fixed"]}, "reason": "r"}),
        factory.make("Record.Voided", {"reason": "dup"}, stream_id="rec-2"),
    ]
    apply_all(engine, *events)
    first_run = fetch_all(engine)
    assert len(first_run) == 2

    with engine.begin() as conn:
        PROJECTOR.reset(conn)
    assert fetch_all(engine) == []

    apply_all(engine, *events)
    assert fetch_all(engine) == first_run


def test_default_registry_routes_record_created_to_core_record() -> None:
    names = [projector.name for projector in default_registry().for_event("Record.Created")]
    assert "core_record" in names
