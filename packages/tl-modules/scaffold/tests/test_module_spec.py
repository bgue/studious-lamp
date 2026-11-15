"""The scaffold module spec and its projector (P2-I4B S1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text
from tl_core.auth.access_words import table_word
from tl_core.ledger import Event
from tl_core.modules import ModuleSpec, load_modules
from tl_core.projection.record import RecordProjector
from tl_mod_scaffold import MODULE
from tl_mod_scaffold.module import (
    SCAFFOLD_COMMANDS,
    SCAFFOLD_GENERIC_COMMANDS,
    projectors,
    spec,
)
from tl_mod_scaffold.names import (
    INSPECTION,
    INSPECTION_TABLE,
    SCAFFOLD,
    SCAFFOLD_EVENTS,
    SCAFFOLD_TABLE,
)
from tl_mod_scaffold.projectors import ScaffoldProjector

BASE = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
STREAM = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2"
INSPECTION_ID = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P4"
REQUEST = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3"
WORDS = {
    "RegisterScaffold": ("scaffold.register", "user"),
    "DesignScaffold": ("scaffold.design", "user"),
    "ErectScaffold": ("scaffold.erect", "user"),
    "InspectScaffold": ("scaffold.inspect", "user"),
    "TagScaffoldGreen": ("scaffold.tag.green", "controller"),
    "ReleaseScaffold": ("scaffold.release", "user"),
    "ModifyScaffold": ("scaffold.modify", "user"),
    "DismantleScaffold": ("scaffold.dismantle", "user"),
    "RemoveScaffold": ("scaffold.remove", "user"),
}


def test_spec_loads_with_both_record_types_and_one_projector() -> None:
    built = spec()
    assert isinstance(built, ModuleSpec)
    assert built.name == MODULE == "scaffold"
    assert built.record_types == frozenset({SCAFFOLD, INSPECTION})
    assert [type(p) for p in built.projectors()] == [ScaffoldProjector]
    assert [type(p) for p in projectors()] == [ScaffoldProjector]


def test_spec_has_nine_commands_each_with_its_word_and_no_drafts_nor_proposals() -> None:
    built = spec()
    assert [c.model.__name__ for c in SCAFFOLD_COMMANDS] == list(WORDS)
    assert dict(built.command_words) == {name: word for name, (word, _) in WORDS.items()}
    for name, (word, table) in WORDS.items():
        assert table_word(word) == table, name
    assert dict(built.offline_drafts) == {}
    assert list(built.proposable) == []
    assert not built.company_roles


def test_generic_commands_are_the_few_and_only_for_the_scaffold() -> None:
    built = spec()
    assert dict(built.generic_commands) == {SCAFFOLD: SCAFFOLD_GENERIC_COMMANDS}
    assert SCAFFOLD_GENERIC_COMMANDS >= {"SetPsetValues", "AddLink", "AttachFile"}
    for forbidden in ("UpdateRecord", "VoidRecord", "TransitionWorkflow"):
        assert forbidden not in SCAFFOLD_GENERIC_COMMANDS
    assert INSPECTION not in built.generic_commands
    assert set(built.generic_guards) == {(SCAFFOLD, c) for c in SCAFFOLD_GENERIC_COMMANDS}


def test_the_platform_discovers_the_module_through_its_entry_point() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert by_name["scaffold"].record_types == frozenset({SCAFFOLD, INSPECTION})


def test_projector_handles_exactly_the_nine_events() -> None:
    assert ScaffoldProjector.handles == SCAFFOLD_EVENTS
    assert len(SCAFFOLD_EVENTS) == 9


class Feed:
    def __init__(self) -> None:
        self.seq = 0
        self.version = 0

    def make(self, event_type: str, payload: dict[str, Any], actor: str = "user:uma") -> Event:
        self.seq += 1
        self.version += 1
        at = BASE + timedelta(minutes=self.seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=self.seq,
            event_id=f"EVT{self.seq:06d}",
            stream_id=STREAM,
            stream_type=SCAFFOLD,
            stream_version=self.version,
            scope="project:P123",
            actor=actor,
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
        for stmt in RecordProjector().ddl(dialect) + ScaffoldProjector().ddl(dialect):
            conn.execute(text(stmt))
    yield eng
    eng.dispose()


def _apply(engine: Engine, *events: Event) -> None:
    record, scaffold = RecordProjector(), ScaffoldProjector()
    for event in events:
        with engine.begin() as conn:
            (scaffold if event.event_type in scaffold.handles else record).apply(conn, event)


def _row(engine: Engine, table: str = SCAFFOLD_TABLE, key: str = STREAM) -> dict[str, Any]:
    with engine.connect() as conn:
        found = conn.execute(text(f"SELECT * FROM {table} WHERE id = :id"), {"id": key})
        return dict(found.mappings().one())


def _created(feed: Feed) -> Event:
    return feed.make(
        "Record.Created",
        {
            "record_type": SCAFFOLD,
            "key": "P123-SCF-0001",
            "title": "Scaffold A",
            "description": None,
            "psets": {},
        },
    )


def _registered(feed: Feed) -> Event:
    return feed.make(
        "Scaffold.Registered",
        {
            "record_id": STREAM,
            "request_id": REQUEST,
            "for_record_id": None,
            "location_text": "North",
            "elevation": "+12.0",
            "gridline": "C-4",
            "load_class": "Light",
            "feed_policy": "none",
        },
    )


def test_round_trip_register_erect_inspect_flag(engine: Engine) -> None:
    feed = Feed()
    _apply(engine, _created(feed), _registered(feed))
    row = _row(engine)
    assert (row["request_id"], row["location_text"], row["elevation"]) == (
        REQUEST,
        "North",
        "+12.0",
    )
    assert (row["gridline"], row["load_class"]) == ("C-4", "Light")
    assert row["tag"] is None and row["inspection_count"] == 0 and row["next_due_on"] is None

    _apply(
        engine,
        feed.make(
            "Scaffold.Erecting",
            {"record_id": STREAM, "note": None, "next_due_on": "2026-12-08", "feed_policy": "none"},
        ),
    )
    assert _row(engine)["next_due_on"] == "2026-12-08"

    _apply(
        engine,
        feed.make(
            "Scaffold.Inspected",
            {
                "record_id": STREAM,
                "inspection_id": INSPECTION_ID,
                "result": "conditional",
                "tag": "yellow",
                "inspected_on": "2026-12-03",
                "next_due_on": "2026-12-10",
                "note": "Toe boards",
                "at": "2026-12-03T08:00:00Z",
                "feed_policy": "none",
            },
            actor="user:rob",
        ),
    )
    row = _row(engine)
    assert (row["tag"], row["tagged_on"], row["last_inspected_on"]) == (
        "yellow",
        "2026-12-03",
        "2026-12-03",
    )
    assert (row["next_due_on"], row["inspection_count"]) == ("2026-12-10", 1)
    inspection = _row(engine, INSPECTION_TABLE, INSPECTION_ID)
    assert inspection["scaffold_id"] == STREAM and inspection["inspector"] == "user:rob"
    assert (inspection["result"], inspection["tag"], inspection["note"]) == (
        "conditional",
        "yellow",
        "Toe boards",
    )
    assert inspection["inspected_on"] == "2026-12-03" and inspection["scope"] == "project:P123"

    _apply(
        engine,
        feed.make(
            "Scaffold.InspectionDue",
            {"record_id": STREAM, "due_on": "2026-12-10", "state": "In Use", "feed_policy": "none"},
            actor="svc:scaffold.inspections_due",
        ),
    )
    row = _row(engine)
    assert row["flagged_due_on"] == "2026-12-10" and row["tag"] == "yellow"
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT version FROM cur_core_record WHERE id = :id"), {"id": STREAM}
        ).scalar_one()
    assert version == feed.version


def test_modify_dismantle_and_the_quiet_events(engine: Engine) -> None:
    feed = Feed()
    _apply(engine, _created(feed), _registered(feed))
    quiet = {"record_id": STREAM, "feed_policy": "none"}
    _apply(
        engine,
        feed.make("Scaffold.Designed", {**quiet, "note": None}),
        feed.make("Scaffold.Released", quiet),
        feed.make("Scaffold.Modified", {**quiet, "reason": "Add a lift"}),
        feed.make("Scaffold.DismantleStarted", {**quiet, "reason": "Done"}),
        feed.make("Scaffold.Removed", {**quiet, "reason": None}),
    )
    row = _row(engine)
    assert (row["modify_reason"], row["dismantle_reason"]) == ("Add a lift", "Done")
    assert row["elevation"] == "+12.0"


def test_reset_clears_both_tables(engine: Engine) -> None:
    feed = Feed()
    _apply(engine, _created(feed), _registered(feed))
    with engine.begin() as conn:
        ScaffoldProjector().reset(conn)
        assert conn.execute(text(f"SELECT count(*) FROM {SCAFFOLD_TABLE}")).scalar_one() == 0
        assert conn.execute(text(f"SELECT count(*) FROM {INSPECTION_TABLE}")).scalar_one() == 0


def test_an_event_for_a_missing_row_is_a_broken_stream(engine: Engine) -> None:
    feed = Feed()
    with pytest.raises(LookupError):
        _apply(
            engine,
            feed.make(
                "Scaffold.Modified", {"record_id": STREAM, "reason": "r", "feed_policy": "none"}
            ),
        )
