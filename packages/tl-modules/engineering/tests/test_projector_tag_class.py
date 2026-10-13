"""TagClassProjector: the TagClass.* events into cur_engineering_tag_class."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import COMPANY, PROJECT, Events, apply, as_json, install, record, rows
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from tl_core.ledger import Event
from tl_mod_engineering.names import (
    TAG_CLASS,
    TAG_CLASS_CLOSED,
    TAG_CLASS_DEFINED,
    TAG_CLASS_REVISED,
    TAG_CLASS_TABLE,
)
from tl_mod_engineering.projectors import TagClassProjector

EDITION = "co.acme.standards@1.0.0"


def define(
    events: Events, stream_id: str, code: str, *, scope: str = COMPANY, **more: Any
) -> list[Event]:
    """The two events a DefineTagClass command appends: the envelope, then the typed fields."""
    payload: dict[str, Any] = {
        "code": code,
        "label": f"{code} label",
        "family": "valve",
        "edition": EDITION,
    }
    payload.update(more)
    return [
        events.created(stream_id, TAG_CLASS, f"TC:{code}@1.0.0", scope=scope),
        events.make(
            TAG_CLASS_DEFINED, payload, stream_id=stream_id, stream_type=TAG_CLASS, scope=scope
        ),
    ]


def revise(events: Events, stream_id: str, changes: dict[str, Any]) -> Event:
    return events.make(
        TAG_CLASS_REVISED,
        {"changes": changes, "reason": "test"},
        stream_id=stream_id,
        stream_type=TAG_CLASS,
        scope=COMPANY,
    )


def close(
    events: Events, stream_id: str, lifecycle: str = "retired", superseded_by: str | None = None
) -> Event:
    return events.make(
        TAG_CLASS_CLOSED,
        {"lifecycle": lifecycle, "superseded_by": superseded_by, "reason": "test"},
        stream_id=stream_id,
        stream_type=TAG_CLASS,
        scope=COMPANY,
    )


def test_it_handles_the_three_tag_class_events_and_names_itself() -> None:
    projector = TagClassProjector()
    assert projector.name == "engineering_tag_class"
    assert projector.handles == frozenset({TAG_CLASS_DEFINED, TAG_CLASS_REVISED, TAG_CLASS_CLOSED})


def test_the_ddl_creates_the_table_and_can_run_twice(engine: Engine, dialect: str) -> None:
    for statement in TagClassProjector().ddl(dialect):
        assert statement.endswith(";")
    install(engine, dialect)
    assert rows(engine, TAG_CLASS_TABLE) == []


def test_ddl_refuses_an_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="unsupported dialect"):
        TagClassProjector().ddl("mysql")


def test_defined_inserts_one_row_with_the_lists_as_json(engine: Engine, events: Events) -> None:
    apply(
        engine,
        *define(
            events,
            "C1",
            "ControlValve",
            required_psets=["valve_data"],
            itr_templates=["ITR-VALVE-01"],
            mnemonics=["FV", "PV"],
        ),
    )
    (row,) = rows(engine, TAG_CLASS_TABLE)
    assert (row["id"], row["scope"], row["code"]) == ("C1", COMPANY, "ControlValve")
    assert (row["label"], row["family"]) == ("ControlValve label", "valve")
    assert as_json(row["required_psets_json"]) == ["valve_data"]
    assert as_json(row["itr_templates_json"]) == ["ITR-VALVE-01"]
    assert as_json(row["mnemonics_json"]) == ["FV", "PV"]
    assert (row["lifecycle"], row["superseded_by"]) == ("active", None)
    assert (row["edition"], row["last_seq"]) == (EDITION, 2)


def test_missing_lists_are_stored_as_empty_lists(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "C1", "Pump"))
    (row,) = rows(engine, TAG_CLASS_TABLE)
    assert as_json(row["required_psets_json"]) == []
    assert as_json(row["itr_templates_json"]) == []
    assert as_json(row["mnemonics_json"]) == []


def test_the_row_moves_the_envelope_to_the_version_of_the_event(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "C1", "Pump"))
    envelope = record(engine, "C1")
    assert envelope["type"] == TAG_CLASS
    assert (envelope["version"], envelope["last_seq"]) == (2, 2)


def test_revised_applies_each_changed_field_to_its_column(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "C1", "ControlValve", required_psets=["valve_data"]))
    apply(
        engine,
        revise(
            events,
            "C1",
            {
                "label": ["ControlValve label", "Control valve"],
                "family": ["valve", "instrument"],
                "required_psets": [["valve_data"], ["valve_data", "safety_data"]],
                "itr_templates": [[], ["ITR-1"]],
                "mnemonics": [[], ["FV"]],
            },
        ),
    )
    (row,) = rows(engine, TAG_CLASS_TABLE)
    assert (row["label"], row["family"]) == ("Control valve", "instrument")
    assert as_json(row["required_psets_json"]) == ["valve_data", "safety_data"]
    assert as_json(row["itr_templates_json"]) == ["ITR-1"]
    assert as_json(row["mnemonics_json"]) == ["FV"]
    assert row["last_seq"] == 3
    assert record(engine, "C1")["version"] == 3


def test_revised_with_an_unknown_field_raises_and_changes_nothing(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "C1", "ControlValve"))
    with pytest.raises(ValueError, match="unsupported field"):
        apply(engine, revise(events, "C1", {"label": ["a", "b"], "code": ["x", "y"]}))
    (row,) = rows(engine, TAG_CLASS_TABLE)
    assert (row["label"], row["code"]) == ("ControlValve label", "ControlValve")


def test_revising_an_unknown_class_raises(engine: Engine, events: Events) -> None:
    apply(engine, events.created("C1", TAG_CLASS, "TC:X@1.0.0", scope=COMPANY))
    with pytest.raises(LookupError):
        apply(engine, revise(events, "C1", {"label": ["a", "b"]}))


def test_closed_sets_the_lifecycle(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "C1", "ControlValve"))
    apply(engine, close(events, "C1", "superseded", "C2"))
    (row,) = rows(engine, TAG_CLASS_TABLE)
    assert (row["lifecycle"], row["superseded_by"]) == ("superseded", "C2")
    assert record(engine, "C1")["version"] == 3


def test_closing_an_unknown_class_raises_and_changes_nothing(
    engine: Engine, events: Events
) -> None:
    apply(engine, events.created("C1", TAG_CLASS, "TC:X@1.0.0", scope=COMPANY))
    with pytest.raises(LookupError):
        apply(engine, close(events, "C1"))
    assert record(engine, "C1")["version"] == 1


def test_a_class_is_defined_once_per_scope(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "C1", "ControlValve"))
    with pytest.raises(IntegrityError):
        apply(engine, *define(events, "C2", "ControlValve"))
    apply(engine, *define(events, "C3", "ControlValve", scope=PROJECT))
    assert [r["id"] for r in rows(engine, TAG_CLASS_TABLE)] == ["C1", "C3"]


def test_reset_empties_the_table_and_a_replay_gives_the_same_rows(
    engine: Engine, events: Events
) -> None:
    stream = [
        *define(events, "C1", "ControlValve", required_psets=["valve_data"]),
        *define(events, "C2", "Pump", family="pump"),
        revise(events, "C1", {"mnemonics": [[], ["FV"]]}),
        close(events, "C2"),
    ]
    apply(engine, *stream)
    first = rows(engine, TAG_CLASS_TABLE)
    projector = TagClassProjector()
    with engine.begin() as conn:
        projector.reset(conn)
    assert rows(engine, TAG_CLASS_TABLE) == []
    with engine.begin() as conn:
        for event in stream:
            if event.event_type in projector.handles:
                projector.apply(conn, event)
    assert rows(engine, TAG_CLASS_TABLE) == first


def test_an_event_it_does_not_handle_is_refused(engine: Engine, events: Events) -> None:
    other = events.make("Tag.Defined", {}, stream_id="C1", stream_type=TAG_CLASS)
    with engine.begin() as conn, pytest.raises(ValueError, match="cannot apply"):
        TagClassProjector().apply(conn, other)
