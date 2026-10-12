"""TagProjector: the Tag.* events into cur_engineering_tag, and the envelope's conformance."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import PROJECT, Events, apply, as_json, install, record, rows
from sqlalchemy import Engine
from tl_core.ledger import Event
from tl_mod_engineering.names import (
    TAG,
    TAG_DEFINED,
    TAG_RECLASSIFIED,
    TAG_SUPERSEDED,
    TAG_TABLE,
)
from tl_mod_engineering.projectors import TagProjector


def define(events: Events, stream_id: str, number: str, **more: Any) -> list[Event]:
    """The two events a CreateTag command appends: the envelope, then the typed fields."""
    payload: dict[str, Any] = {
        "number": number,
        "class_code": "ControlValve",
        "area": "47",
        "mnemonic": "FV",
        "sequence": 1001,
        "segments": {"area": "47", "mnemonic": "FV", "seq": "1001"},
        "pattern_code": "tag",
        "number_status": "ok",
        "violations": [],
        "origin": "created",
        "supersedes": [],
        "bound_psets": ["valve_data"],
        "conformance": "nonconformant",
        "effective_schema_hash": "hash-1",
    }
    payload.update(more)
    return [
        events.created(stream_id, TAG, number),
        events.make(TAG_DEFINED, payload, stream_id=stream_id, stream_type=TAG),
    ]


def reclassify(events: Events, stream_id: str, **more: Any) -> Event:
    payload: dict[str, Any] = {
        "from_class": "ControlValve",
        "to_class": "ManualValve",
        "conformance": "ok",
        "effective_schema_hash": "hash-2",
    }
    payload.update(more)
    return events.make(TAG_RECLASSIFIED, payload, stream_id=stream_id, stream_type=TAG)


def supersede(events: Events, stream_id: str, **more: Any) -> Event:
    payload: dict[str, Any] = {"operation": "rename", "superseded_by": ["T2"], "reason": "test"}
    payload.update(more)
    return events.make(TAG_SUPERSEDED, payload, stream_id=stream_id, stream_type=TAG)


def test_it_handles_the_three_tag_events_and_names_itself() -> None:
    projector = TagProjector()
    assert projector.name == "engineering_tag"
    assert projector.handles == frozenset({TAG_DEFINED, TAG_RECLASSIFIED, TAG_SUPERSEDED})


def test_the_ddl_creates_the_table_and_can_run_twice(engine: Engine, dialect: str) -> None:
    for statement in TagProjector().ddl(dialect):
        assert statement.endswith(";")
    install(engine, dialect)
    assert rows(engine, TAG_TABLE) == []


def test_ddl_refuses_an_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="unsupported dialect"):
        TagProjector().ddl("mysql")


def test_defined_inserts_one_row_with_the_parsed_segments(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "T1", "47-FV-1001"))
    (row,) = rows(engine, TAG_TABLE)
    assert (row["id"], row["scope"], row["number"]) == ("T1", PROJECT, "47-FV-1001")
    assert (row["class_code"], row["area"], row["mnemonic"]) == ("ControlValve", "47", "FV")
    assert row["sequence"] == 1001
    assert as_json(row["segments_json"]) == {"area": "47", "mnemonic": "FV", "seq": "1001"}
    assert (row["pattern_code"], row["number_status"], row["origin"]) == ("tag", "ok", "created")
    assert as_json(row["violations_json"]) == []
    assert row["last_seq"] == 2


def test_a_number_that_did_not_parse_keeps_null_segments(engine: Engine, events: Events) -> None:
    apply(
        engine,
        *define(
            events,
            "T1",
            "LEGACY-7",
            class_code=None,
            area=None,
            mnemonic=None,
            sequence=None,
            segments={},
            pattern_code=None,
            number_status="violation",
            violations=["does not fit pattern tag"],
            origin="import",
        ),
    )
    (row,) = rows(engine, TAG_TABLE)
    for column in ("class_code", "area", "mnemonic", "sequence", "pattern_code"):
        assert row[column] is None, column
    assert as_json(row["segments_json"]) == {}
    assert (row["number_status"], row["origin"]) == ("violation", "import")
    assert as_json(row["violations_json"]) == ["does not fit pattern tag"]


def test_defined_copies_the_conformance_and_schema_hash_to_the_envelope(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "T1", "47-FV-1001"))
    envelope = record(engine, "T1")
    assert envelope["type"] == TAG
    assert (envelope["conformance"], envelope["effective_schema_hash"]) == (
        "nonconformant",
        "hash-1",
    )
    assert (envelope["version"], envelope["last_seq"]) == (2, 2)


def test_without_a_conformance_in_the_event_the_envelope_keeps_its_value(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "T1", "47-FV-1001", conformance=None, effective_schema_hash=None))
    envelope = record(engine, "T1")
    assert (envelope["conformance"], envelope["effective_schema_hash"]) == ("ok", None)


def test_reclassified_changes_the_class_and_the_envelope(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "T1", "47-FV-1001"))
    apply(engine, reclassify(events, "T1"))
    (row,) = rows(engine, TAG_TABLE)
    assert (row["class_code"], row["last_seq"]) == ("ManualValve", 3)
    envelope = record(engine, "T1")
    assert (envelope["conformance"], envelope["effective_schema_hash"]) == ("ok", "hash-2")
    assert envelope["version"] == 3


def test_superseded_changes_no_typed_column_but_moves_the_version(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "T1", "47-FV-1001"))
    before = rows(engine, TAG_TABLE)[0]
    apply(engine, supersede(events, "T1"))
    after = rows(engine, TAG_TABLE)[0]
    assert {k: v for k, v in after.items() if k != "last_seq"} == {
        k: v for k, v in before.items() if k != "last_seq"
    }
    assert after["last_seq"] == 3
    envelope = record(engine, "T1")
    assert envelope["version"] == 3
    assert envelope["conformance"] == "nonconformant"  # the event carries none: unchanged


def test_an_event_for_an_unknown_tag_raises_and_changes_nothing(
    engine: Engine, events: Events
) -> None:
    apply(engine, events.created("T1", TAG, "47-FV-1001"))
    with pytest.raises(LookupError):
        apply(engine, reclassify(events, "T1"))
    assert rows(engine, TAG_TABLE) == []
    assert record(engine, "T1")["version"] == 1


def test_the_pair_of_events_needs_the_envelope_first(engine: Engine, events: Events) -> None:
    orphan = events.make(
        TAG_DEFINED,
        {"number": "X", "number_status": "ok", "origin": "created"},
        stream_id="T9",
        stream_type=TAG,
    )
    with pytest.raises(LookupError):
        apply(engine, orphan)
    assert rows(engine, TAG_TABLE) == []


def test_reset_empties_the_table_and_a_replay_gives_the_same_rows(
    engine: Engine, events: Events
) -> None:
    stream = [
        *define(events, "T1", "47-FV-1001"),
        *define(events, "T2", "47-FV-1002"),
        reclassify(events, "T1"),
        supersede(events, "T2"),
    ]
    apply(engine, *stream)
    first = rows(engine, TAG_TABLE)
    projector = TagProjector()
    with engine.begin() as conn:
        projector.reset(conn)
    assert rows(engine, TAG_TABLE) == []
    with engine.begin() as conn:
        for event in stream:
            if event.event_type in projector.handles:
                projector.apply(conn, event)
    assert rows(engine, TAG_TABLE) == first


def test_an_event_it_does_not_handle_is_refused(engine: Engine, events: Events) -> None:
    other = events.make("Standard.Defined", {}, stream_id="T1", stream_type=TAG)
    with engine.begin() as conn, pytest.raises(ValueError, match="cannot apply"):
        TagProjector().apply(conn, other)
