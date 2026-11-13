"""The quality module spec and the punch item projector (P2-PUNCH S1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text
from tl_core.ledger import Event
from tl_core.modules import ModuleSpec, load_modules
from tl_core.projection.record import RecordProjector
from tl_mod_quality import MODULE
from tl_mod_quality.module import PUNCH_COMMANDS, projectors, spec
from tl_mod_quality.names import PUNCH_EVENTS, PUNCH_ITEM, PUNCH_ITEM_TABLE
from tl_mod_quality.projectors import PunchItemProjector

BASE = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
STREAM = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2"


def test_spec_loads_with_the_record_type_and_one_projector() -> None:
    built = spec()
    assert isinstance(built, ModuleSpec)
    assert built.name == MODULE == "quality"
    assert built.record_types == frozenset({PUNCH_ITEM})
    assert [type(p) for p in built.projectors()] == [PunchItemProjector]
    assert [type(p) for p in projectors()] == [PunchItemProjector]


def test_spec_has_six_commands_and_the_raise_draft() -> None:
    built = spec()
    assert [c.model.__name__ for c in PUNCH_COMMANDS] == [
        "RaisePunchItem",
        "EditPunchItem",
        "ClearPunchItem",
        "VerifyPunchItem",
        "ReopenPunchItem",
        "VoidPunchItem",
    ]
    assert dict(built.command_words) == {c.model.__name__: c.access for c in PUNCH_COMMANDS}
    assert dict(built.offline_drafts) == {PUNCH_ITEM: frozenset({"RaisePunchItem"})}
    assert not built.company_roles


def test_the_platform_discovers_the_module_through_its_entry_point() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert PUNCH_ITEM in by_name["quality"].record_types


def test_projector_handles_exactly_the_six_events() -> None:
    assert PunchItemProjector.handles == PUNCH_EVENTS
    assert len(PUNCH_EVENTS) == 6


class Feed:
    def __init__(self) -> None:
        self.seq = 0
        self.version = 0

    def make(self, event_type: str, payload: dict[str, Any]) -> Event:
        self.seq += 1
        self.version += 1
        at = BASE + timedelta(minutes=self.seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=self.seq,
            event_id=f"EVT{self.seq:06d}",
            stream_id=STREAM,
            stream_type=PUNCH_ITEM,
            stream_version=self.version,
            scope="project:P123",
            actor="user:uma",
            recorded_at=at,
            effective_at=at,
            correlation_id="corr-1",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"hash-{self.seq}",
        )


@pytest.fixture
def engine(new_engine: Callable[[], Engine], dialect: str) -> Iterator[Engine]:
    eng = new_engine()
    with eng.begin() as conn:
        for stmt in RecordProjector().ddl(dialect) + PunchItemProjector().ddl(dialect):
            conn.execute(text(stmt))
    yield eng
    eng.dispose()


def _apply(engine: Engine, *events: Event) -> None:
    record, punch = RecordProjector(), PunchItemProjector()
    for event in events:
        with engine.begin() as conn:
            (punch if event.event_type in punch.handles else record).apply(conn, event)


def _row(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        found = (
            conn.execute(text(f"SELECT * FROM {PUNCH_ITEM_TABLE} WHERE id = :id"), {"id": STREAM})
            .mappings()
            .one()
        )
    return dict(found)


def _created(feed: Feed) -> Event:
    return feed.make(
        "Record.Created",
        {
            "record_type": PUNCH_ITEM,
            "key": "P123-PUN-0001",
            "title": "Guard missing",
            "description": "Pump P-101",
            "psets": {},
        },
    )


def _raised(feed: Feed, **over: Any) -> Event:
    payload: dict[str, Any] = {
        "record_id": STREAM,
        "area": "A1",
        "system": "47-01",
        "due_on": "2026-12-20",
        "category": "A",
        "assignee": "user:rob",
        "raised_by": "user:uma",
        "source_id": None,
        "feed_policy": "none",
    }
    payload.update(over)
    return feed.make("PunchItem.Raised", payload)


def test_round_trip_raise_clear_reopen(engine: Engine) -> None:
    feed = Feed()
    _apply(engine, _created(feed), _raised(feed))
    row = _row(engine)
    assert (row["area"], row["system"], row["category"], row["raised_by"]) == (
        "A1",
        "47-01",
        "A",
        "user:uma",
    )
    assert row["reopen_count"] == 0 and row["cleared_by"] is None

    _apply(
        engine,
        feed.make(
            "PunchItem.Cleared",
            {
                "record_id": STREAM,
                "by": "user:rob",
                "note": "Guard fitted",
                "at": "2026-12-02T09:30:00Z",
                "feed_policy": "none",
            },
        ),
    )
    row = _row(engine)
    assert (row["cleared_by"], row["cleared_on"], row["clear_note"]) == (
        "user:rob",
        "2026-12-02",
        "Guard fitted",
    )

    _apply(
        engine,
        feed.make(
            "PunchItem.Verified",
            {
                "record_id": STREAM,
                "by": "user:sue",
                "at": "2026-12-03T14:00:00Z",
                "feed_policy": "none",
            },
        ),
    )
    assert _row(engine)["verified_on"] == "2026-12-03"

    _apply(
        engine,
        feed.make(
            "PunchItem.Reopened",
            {"record_id": STREAM, "by": "user:sue", "reason": "Guard loose", "feed_policy": "none"},
        ),
    )
    row = _row(engine)
    assert row["reopen_count"] == 1
    assert row["last_reopen_reason"] == "Guard loose"
    for column in ("cleared_by", "cleared_on", "clear_note", "verified_by", "verified_on"):
        assert row[column] is None, column
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT version FROM cur_core_record WHERE id = :id"), {"id": STREAM}
        ).scalar_one()
    assert version == feed.version


def test_reopen_twice_counts_two(engine: Engine) -> None:
    feed = Feed()
    _apply(engine, _created(feed), _raised(feed))
    for _ in range(2):
        _apply(
            engine,
            feed.make(
                "PunchItem.Reopened",
                {"record_id": STREAM, "by": "user:sue", "reason": "again", "feed_policy": "none"},
            ),
        )
    assert _row(engine)["reopen_count"] == 2


def test_edit_and_void(engine: Engine) -> None:
    feed = Feed()
    _apply(engine, _created(feed), _raised(feed, category=None))
    assert _row(engine)["category"] == "B"
    _apply(
        engine,
        feed.make(
            "PunchItem.Edited",
            {
                "record_id": STREAM,
                "changes": {"area": ["A1", "A2"], "assignee": ["user:rob", "user:ann"]},
                "feed_policy": "none",
            },
        ),
        feed.make(
            "PunchItem.Voided",
            {
                "record_id": STREAM,
                "by": "user:sue",
                "reason": "Raised twice",
                "feed_policy": "none",
            },
        ),
    )
    row = _row(engine)
    assert (row["area"], row["assignee"], row["void_reason"]) == ("A2", "user:ann", "Raised twice")
    assert row["system"] == "47-01"


def test_an_event_for_a_missing_row_is_a_broken_stream(engine: Engine) -> None:
    feed = Feed()
    with pytest.raises(LookupError):
        _apply(
            engine,
            feed.make(
                "PunchItem.Voided",
                {"record_id": STREAM, "by": "u", "reason": "r", "feed_policy": "none"},
            ),
        )
