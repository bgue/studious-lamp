"""StandardProjector: Standard.Defined and Standard.Closed into cur_engineering_standard."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import COMPANY, Events, apply, as_json, install, record, rows
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from tl_core.ledger import Event
from tl_mod_engineering.names import (
    CODE_LIST,
    MNEMONIC,
    NUMBERING_PATTERN,
    STANDARD_CLOSED,
    STANDARD_DEFINED,
    STANDARD_TABLE,
)
from tl_mod_engineering.projectors import StandardProjector

EDITION = "co.acme.standards@1.0.0"


def defined_payload(kind: str, code: str, **more: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": kind,
        "code": code,
        "label": f"{code} label",
        "edition": EDITION,
    }
    payload.update(more)
    return payload


def define(
    events: Events,
    stream_id: str,
    record_type: str,
    kind: str,
    code: str,
    **more: Any,
) -> list[Event]:
    """The two events a registry command appends: the envelope, then the typed fields.

    The record key is ``<kind>:<code>@<edition version>``, unique per scope across editions.
    """
    payload = defined_payload(kind, code, **more)
    key = f"{kind}:{code}@{payload['edition'].split('@')[1]}"
    return [
        events.created(stream_id, record_type, key, scope=COMPANY),
        events.make(
            STANDARD_DEFINED,
            payload,
            stream_id=stream_id,
            stream_type=record_type,
            scope=COMPANY,
        ),
    ]


def close(events: Events, stream_id: str, record_type: str, **payload: Any) -> Event:
    body: dict[str, Any] = {"lifecycle": "retired", "reason": "test"}
    body.update(payload)
    return events.make(
        STANDARD_CLOSED, body, stream_id=stream_id, stream_type=record_type, scope=COMPANY
    )


def test_it_handles_the_two_standard_events_and_names_itself() -> None:
    projector = StandardProjector()
    assert projector.name == "engineering_standard"
    assert projector.handles == frozenset({STANDARD_DEFINED, STANDARD_CLOSED})


def test_the_ddl_creates_the_table_and_can_run_twice(engine: Engine, dialect: str) -> None:
    for statement in StandardProjector().ddl(dialect):
        assert statement.endswith(";")
    install(engine, dialect)  # a second time: every statement is IF NOT EXISTS
    assert rows(engine, STANDARD_TABLE) == []


def test_ddl_refuses_an_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="unsupported dialect"):
        StandardProjector().ddl("mysql")


def test_defined_inserts_one_row_with_every_column(engine: Engine, events: Events) -> None:
    apply(
        engine,
        *define(
            events,
            "S1",
            CODE_LIST,
            "code_list",
            "Discipline",
            definition="Engineering disciplines",
            owner="role:steward",
            adoption="mandatory",
            value_list_policy="closed",
            effective_from="2026-01-01",
            effective_to="2030-12-31",
            data={"note": "x"},
        ),
    )
    (row,) = rows(engine, STANDARD_TABLE)
    assert row["id"] == "S1"
    assert row["scope"] == COMPANY
    assert (row["kind"], row["code"], row["label"]) == (
        "code_list",
        "Discipline",
        "Discipline label",
    )
    assert row["definition"] == "Engineering disciplines"
    assert (row["edition"], row["owner"]) == (EDITION, "role:steward")
    assert (row["adoption"], row["value_list_policy"]) == ("mandatory", "closed")
    assert (row["effective_from"], row["effective_to"]) == ("2026-01-01", "2030-12-31")
    assert (row["lifecycle"], row["superseded_by"]) == ("active", None)
    assert as_json(row["data_json"]) == {"note": "x"}
    assert row["last_seq"] == 2


def test_missing_optional_fields_take_the_documented_defaults(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "S1", MNEMONIC, "mnemonic", "FV"))
    (row,) = rows(engine, STANDARD_TABLE)
    assert row["adoption"] == "default"
    assert as_json(row["data_json"]) == {}
    for column in ("definition", "owner", "value_list_policy", "effective_from", "effective_to"):
        assert row[column] is None, column


def test_the_row_moves_the_envelope_to_the_version_of_the_event(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "S1", NUMBERING_PATTERN, "numbering_pattern", "tag"))
    envelope = record(engine, "S1")
    assert envelope["type"] == NUMBERING_PATTERN
    assert (envelope["version"], envelope["last_seq"]) == (2, 2)
    assert envelope["updated_at"] > envelope["created_at"]


def test_closed_marks_the_entry_and_keeps_the_end_date_when_none_is_given(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "S1", CODE_LIST, "code_list", "Craft", effective_to="2029-01-01"))
    apply(engine, close(events, "S1", CODE_LIST, lifecycle="superseded", superseded_by="S2"))
    (row,) = rows(engine, STANDARD_TABLE)
    assert (row["lifecycle"], row["superseded_by"]) == ("superseded", "S2")
    assert row["effective_to"] == "2029-01-01"
    assert row["last_seq"] == 3
    assert record(engine, "S1")["version"] == 3


def test_closed_with_an_end_date_replaces_it(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "S1", CODE_LIST, "code_list", "Craft"))
    apply(engine, close(events, "S1", CODE_LIST, effective_to="2028-06-30"))
    (row,) = rows(engine, STANDARD_TABLE)
    assert (row["lifecycle"], row["effective_to"]) == ("retired", "2028-06-30")


def test_closing_an_unknown_entry_raises_and_changes_nothing(
    engine: Engine, events: Events
) -> None:
    apply(engine, events.created("S1", CODE_LIST, "code_list:Craft", scope=COMPANY))
    with pytest.raises(LookupError):
        apply(engine, close(events, "S1", CODE_LIST))
    assert rows(engine, STANDARD_TABLE) == []
    assert record(engine, "S1")["version"] == 1


def test_a_second_entry_with_the_same_kind_code_and_edition_is_refused(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "S1", MNEMONIC, "mnemonic", "FV"))
    with pytest.raises(IntegrityError):
        apply(engine, *define(events, "S2", MNEMONIC, "mnemonic", "FV"))
    assert [r["id"] for r in rows(engine, STANDARD_TABLE)] == ["S1"]


def test_the_same_code_in_another_edition_or_kind_is_allowed(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "S1", MNEMONIC, "mnemonic", "FV"))
    apply(
        engine, *define(events, "S2", MNEMONIC, "mnemonic", "FV", edition="co.acme.standards@2.0.0")
    )
    apply(engine, *define(events, "S3", CODE_LIST, "code_list", "FV"))
    assert [r["id"] for r in rows(engine, STANDARD_TABLE)] == ["S1", "S2", "S3"]


def test_reset_empties_the_table_and_a_replay_gives_the_same_rows(
    engine: Engine, events: Events
) -> None:
    stream = [
        *define(events, "S1", CODE_LIST, "code_list", "Discipline", data={"a": 1}),
        *define(events, "S2", MNEMONIC, "mnemonic", "PT"),
        close(events, "S1", CODE_LIST, lifecycle="superseded", superseded_by="S2"),
    ]
    apply(engine, *stream)
    first = rows(engine, STANDARD_TABLE)
    projector = StandardProjector()
    with engine.begin() as conn:
        projector.reset(conn)
    assert rows(engine, STANDARD_TABLE) == []
    with engine.begin() as conn:
        for event in stream:
            if event.event_type in projector.handles:
                projector.apply(conn, event)
    assert rows(engine, STANDARD_TABLE) == first


def test_an_event_it_does_not_handle_is_refused(engine: Engine, events: Events) -> None:
    other = events.make("Tag.Defined", {}, stream_id="S1", stream_type=MNEMONIC, scope=COMPANY)
    with engine.begin() as conn, pytest.raises(ValueError, match="cannot apply"):
        StandardProjector().apply(conn, other)
