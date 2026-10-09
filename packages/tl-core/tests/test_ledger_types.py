"""Construction, validation, and round-trip tests for ledger value types and shared helpers."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from tl_core.ledger import AppendResult, ConcurrencyError, Event, NewEvent
from tl_core.util import new_ulid, utcnow

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _event(seq: int, stream_version: int, hash_: str, prev: str | None) -> Event:
    return Event(
        event_type="Record.Created",
        schema_version=1,
        payload={"a": 1},
        seq=seq,
        event_id=new_ulid(),
        stream_id="s1",
        stream_type="record",
        stream_version=stream_version,
        scope="company",
        actor="user:u1",
        recorded_at=NOW,
        effective_at=NOW,
        correlation_id="c1",
        causation_id=None,
        source="test",
        prev_hash=prev,
        hash=hash_,
    )


def test_new_event_requires_event_type_and_payload() -> None:
    with pytest.raises(ValidationError):
        NewEvent.model_validate({"payload": {}})
    with pytest.raises(ValidationError):
        NewEvent.model_validate({"event_type": "Record.Created"})


def test_new_event_defaults() -> None:
    ev = NewEvent(event_type="Record.Created", payload={"a": 1})
    assert ev.schema_version == 1
    assert ev.effective_at is None


def test_event_rejects_missing_hash() -> None:
    without_hash = {
        "event_type": "Record.Created",
        "payload": {},
        "seq": 1,
        "event_id": new_ulid(),
        "stream_id": "s1",
        "stream_type": "record",
        "stream_version": 1,
        "scope": "company",
        "actor": "user:u1",
        "recorded_at": NOW,
        "effective_at": NOW,
        "correlation_id": "c1",
        "causation_id": None,
        "source": "test",
        "prev_hash": None,
    }
    with pytest.raises(ValidationError):
        Event.model_validate(without_hash)


def test_event_round_trips_through_json() -> None:
    ev = _event(seq=1, stream_version=1, hash_="h1", prev=None)
    restored = Event.model_validate_json(ev.model_dump_json())
    assert restored == ev


def test_append_result_new_version_matches_last_event() -> None:
    first = _event(seq=1, stream_version=1, hash_="h1", prev=None)
    second = _event(seq=2, stream_version=2, hash_="h2", prev="h1")
    result = AppendResult(events=[first, second], new_version=2, last_seq=2)
    assert result.new_version == result.events[-1].stream_version
    assert result.last_seq == result.events[-1].seq


def test_concurrency_error_is_exception() -> None:
    assert issubclass(ConcurrencyError, Exception)


def test_utcnow_is_timezone_aware_utc() -> None:
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_new_ulid_is_26_chars_and_unique() -> None:
    first = new_ulid()
    second = new_ulid()
    assert len(first) == 26
    assert len(second) == 26
    assert first != second
