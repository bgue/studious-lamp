"""Query helpers over cur_core_record: get_record and list_records (P0-I1-T11)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.ledger import NewEvent
from tl_core.services.queries import get_record, list_records

ENVELOPE_KEYS = {
    "id",
    "key",
    "type",
    "scope",
    "title",
    "description",
    "status",
    "psets",
    "voided",
    "version",
    "last_seq",
    "effective_schema_hash",
    "conformance",
    "created_at",
    "updated_at",
}


def _create(
    db: DbTarget, record_id: str, scope: str, key: str, title: str, psets: dict[str, Any]
) -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id=record_id,
            stream_type="core.Record",
            scope=scope,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": "task", "key": key, "title": title, "psets": psets},
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


def _void(db: DbTarget, record_id: str, scope: str) -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id=record_id,
            stream_type="core.Record",
            scope=scope,
            expected_version=1,
            events=[NewEvent(event_type="Record.Voided", payload={"reason": "r"})],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


def _set_status(db: DbTarget, record_id: str, scope: str, status: str) -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id=record_id,
            stream_type="core.Record",
            scope=scope,
            expected_version=1,
            events=[
                NewEvent(
                    event_type="Record.Updated",
                    payload={"changes": {"status": [None, status]}},
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


def test_get_record_returns_envelope(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    _create(db, "rec-1", "project:p1", "T-1", "First task", {"a": 1})

    with open_uow(db, readonly=True) as uow:
        record = get_record(uow, "project:p1", "T-1")

    assert record is not None
    assert set(record.keys()) == ENVELOPE_KEYS
    assert record["id"] == "rec-1"
    assert record["key"] == "T-1"
    assert record["type"] == "task"
    assert record["scope"] == "project:p1"
    assert record["title"] == "First task"
    assert record["psets"] == {"a": 1}
    assert record["voided"] is False
    assert record["version"] == 1
    assert isinstance(record["created_at"], str)
    assert isinstance(record["updated_at"], str)


def test_get_record_unknown_key_and_other_scope_return_none(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    _create(db, "rec-1", "project:p1", "T-1", "First task", {})

    with open_uow(db, readonly=True) as uow:
        assert get_record(uow, "project:p1", "T-999") is None
        assert get_record(uow, "project:p2", "T-1") is None


def test_get_record_returns_voided_record(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    _create(db, "rec-1", "project:p1", "T-1", "First task", {})
    _void(db, "rec-1", "project:p1")

    with open_uow(db, readonly=True) as uow:
        record = get_record(uow, "project:p1", "T-1")

    assert record is not None
    assert record["voided"] is True


def test_get_record_reads_status_from_update(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    _create(db, "rec-1", "project:p1", "T-1", "First task", {})
    _set_status(db, "rec-1", "project:p1", "open")

    with open_uow(db, readonly=True) as uow:
        record = get_record(uow, "project:p1", "T-1")

    assert record is not None
    assert record["status"] == "open"
    assert record["version"] == 2


def test_list_records_scope_order_and_voided_filter(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    _create(db, "rec-a", "project:p1", "T-1", "one", {})
    _create(db, "rec-b", "project:p1", "T-2", "two", {})
    _create(db, "rec-c", "project:p1", "T-3", "three", {})
    _create(db, "rec-x", "project:p2", "T-1", "other scope", {})
    _void(db, "rec-b", "project:p1")

    with open_uow(db, readonly=True) as uow:
        visible = list_records(uow, "project:p1")
        everything = list_records(uow, "project:p1", include_voided=True)

    assert [r["id"] for r in visible] == ["rec-a", "rec-c"]
    assert [r["id"] for r in everything] == ["rec-a", "rec-b", "rec-c"]
    assert all(set(r.keys()) == ENVELOPE_KEYS for r in everything)
    assert [r["voided"] for r in everything] == [False, True, False]


def test_list_records_status_filter(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    _create(db, "rec-a", "project:p1", "T-1", "one", {})
    _create(db, "rec-b", "project:p1", "T-2", "two", {})
    _set_status(db, "rec-b", "project:p1", "open")

    with open_uow(db, readonly=True) as uow:
        open_only = list_records(uow, "project:p1", status="open")
        none_matching = list_records(uow, "project:p1", status="closed")

    assert [r["id"] for r in open_only] == ["rec-b"]
    assert none_matching == []


def test_queries_on_empty_table(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)

    with open_uow(db, readonly=True) as uow:
        assert get_record(uow, "project:p1", "T-1") is None
        assert list_records(uow, "project:p1") == []
