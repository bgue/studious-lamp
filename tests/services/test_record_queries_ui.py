"""Query helpers added for the TUI client: by-id, history, type filter, paging (P0-I2-T11)."""

from __future__ import annotations

from pathlib import Path

from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.ledger import NewEvent
from tl_core.services.queries import get_record_by_id, list_records, record_history


def _create(db: Path, record_id: str, key: str, record_type: str = "core.Record") -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id=record_id,
            stream_type="core.Record",
            scope="project:p1",
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": record_type, "key": key, "title": key, "psets": {}},
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


def _seed(db: Path, count: int = 5) -> None:
    create_schema(db)
    for i in range(count):
        _create(db, f"rec-{i}", f"T-{i}", "core.Record" if i % 2 == 0 else "other.Thing")


def test_get_record_by_id(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    _seed(db, 2)
    with open_uow(db, readonly=True) as uow:
        found = get_record_by_id(uow, "rec-1")
        missing = get_record_by_id(uow, "nope")
    assert found is not None
    assert found["key"] == "T-1"
    assert missing is None


def test_record_history_returns_stream_events_in_order(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    _seed(db, 1)
    with open_uow(db) as uow:
        uow.append(
            stream_id="rec-0",
            stream_type="core.Record",
            scope="project:p1",
            expected_version=1,
            events=[
                NewEvent(event_type="Record.Updated", payload={"changes": {"title": ["a", "b"]}})
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )
    with open_uow(db, readonly=True) as uow:
        events = record_history(uow, "rec-0")
        unknown = record_history(uow, "nope")
    assert [e.event_type for e in events] == ["Record.Created", "Record.Updated"]
    assert [e.stream_version for e in events] == [1, 2]
    assert unknown == []


def test_list_records_record_type_filter(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    _seed(db, 5)
    with open_uow(db, readonly=True) as uow:
        core = list_records(uow, "project:p1", record_type="core.Record")
        other = list_records(uow, "project:p1", record_type="other.Thing")
    assert [r["id"] for r in core] == ["rec-0", "rec-2", "rec-4"]
    assert [r["id"] for r in other] == ["rec-1", "rec-3"]


def test_list_records_limit_and_offset(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    _seed(db, 5)
    with open_uow(db, readonly=True) as uow:
        first = list_records(uow, "project:p1", limit=2)
        second = list_records(uow, "project:p1", limit=2, offset=2)
        tail = list_records(uow, "project:p1", offset=3)
        beyond = list_records(uow, "project:p1", limit=2, offset=10)
    assert [r["id"] for r in first] == ["rec-0", "rec-1"]
    assert [r["id"] for r in second] == ["rec-2", "rec-3"]
    assert [r["id"] for r in tail] == ["rec-3", "rec-4"]
    assert beyond == []
