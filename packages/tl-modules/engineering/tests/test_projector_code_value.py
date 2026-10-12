"""CodeValueProjector: CodeValue.Defined and CodeValue.Closed into cur_engineering_code_value."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import COMPANY, PROJECT, Events, apply, as_json, install, record, rows
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from tl_core.ledger import Event
from tl_mod_engineering.names import (
    CODE_VALUE,
    CODE_VALUE_CLOSED,
    CODE_VALUE_DEFINED,
    CODE_VALUE_TABLE,
)
from tl_mod_engineering.projectors import CodeValueProjector

EDITION = "co.acme.standards@1.0.0"


def define(
    events: Events,
    stream_id: str,
    code_list: str,
    code: str,
    *,
    scope: str = COMPANY,
    origin: str = "company",
    **more: Any,
) -> list[Event]:
    """The two events an AddCodeValue command appends: the envelope, then the typed fields."""
    payload: dict[str, Any] = {
        "code_list": code_list,
        "code": code,
        "label": f"{code} label",
        "origin": origin,
        "edition": EDITION,
    }
    payload.update(more)
    return [
        events.created(stream_id, CODE_VALUE, f"{code_list}.{code}", scope=scope),
        events.make(
            CODE_VALUE_DEFINED, payload, stream_id=stream_id, stream_type=CODE_VALUE, scope=scope
        ),
    ]


def close(events: Events, stream_id: str, **payload: Any) -> Event:
    body: dict[str, Any] = {"lifecycle": "retired", "reason": "test"}
    body.update(payload)
    return events.make(
        CODE_VALUE_CLOSED, body, stream_id=stream_id, stream_type=CODE_VALUE, scope=COMPANY
    )


def test_it_handles_the_two_code_value_events_and_names_itself() -> None:
    projector = CodeValueProjector()
    assert projector.name == "engineering_code_value"
    assert projector.handles == frozenset({CODE_VALUE_DEFINED, CODE_VALUE_CLOSED})


def test_the_ddl_creates_the_table_and_can_run_twice(engine: Engine, dialect: str) -> None:
    for statement in CodeValueProjector().ddl(dialect):
        assert statement.endswith(";")
    install(engine, dialect)
    assert rows(engine, CODE_VALUE_TABLE) == []


def test_ddl_refuses_an_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="unsupported dialect"):
        CodeValueProjector().ddl("mysql")


def test_defined_inserts_one_row_with_every_column(engine: Engine, events: Events) -> None:
    apply(
        engine,
        *define(
            events,
            "V1",
            "Discipline",
            "PIP",
            meaning="https://example.org/meaning/piping",
            sort_order=10,
            effective_from="2026-01-01",
            effective_to="2031-01-01",
            attributes={"ucum": "[in_i]"},
        ),
    )
    (row,) = rows(engine, CODE_VALUE_TABLE)
    assert (row["id"], row["scope"]) == ("V1", COMPANY)
    assert (row["code_list"], row["code"], row["label"]) == ("Discipline", "PIP", "PIP label")
    assert row["meaning"] == "https://example.org/meaning/piping"
    assert (row["crosswalk"], row["origin"], row["sort_order"]) == (None, "company", 10)
    assert (row["effective_from"], row["effective_to"]) == ("2026-01-01", "2031-01-01")
    assert (row["lifecycle"], row["superseded_by"], row["edition"]) == ("active", None, EDITION)
    assert as_json(row["attributes_json"]) == {"ucum": "[in_i]"}
    assert row["last_seq"] == 2


def test_missing_optional_fields_take_the_documented_defaults(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "V1", "Discipline", "PIP"))
    (row,) = rows(engine, CODE_VALUE_TABLE)
    assert row["sort_order"] == 0
    assert as_json(row["attributes_json"]) == {}
    for column in ("meaning", "crosswalk", "effective_from", "effective_to"):
        assert row[column] is None, column


def test_a_project_value_keeps_its_scope_and_its_crosswalk(engine: Engine, events: Events) -> None:
    apply(
        engine,
        *define(
            events,
            "V9",
            "MaterialCode",
            "SS316L-NACE",
            scope=PROJECT,
            origin="project",
            crosswalk="SS316L",
        ),
    )
    (row,) = rows(engine, CODE_VALUE_TABLE)
    assert (row["scope"], row["origin"], row["crosswalk"]) == (PROJECT, "project", "SS316L")


def test_the_row_moves_the_envelope_to_the_version_of_the_event(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "V1", "Discipline", "PIP"))
    envelope = record(engine, "V1")
    assert envelope["type"] == CODE_VALUE
    assert (envelope["version"], envelope["last_seq"]) == (2, 2)


def test_closed_supersedes_a_value_and_keeps_the_end_date_when_none_is_given(
    engine: Engine, events: Events
) -> None:
    apply(engine, *define(events, "V1", "Discipline", "PIP", effective_to="2029-01-01"))
    apply(engine, close(events, "V1", lifecycle="superseded", superseded_by="V2"))
    (row,) = rows(engine, CODE_VALUE_TABLE)
    assert (row["lifecycle"], row["superseded_by"]) == ("superseded", "V2")
    assert row["effective_to"] == "2029-01-01"
    assert record(engine, "V1")["version"] == 3


def test_closed_with_an_end_date_replaces_it(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "V1", "Discipline", "PIP"))
    apply(engine, close(events, "V1", effective_to="2028-06-30"))
    (row,) = rows(engine, CODE_VALUE_TABLE)
    assert (row["lifecycle"], row["effective_to"]) == ("retired", "2028-06-30")


def test_closing_an_unknown_value_raises_and_changes_nothing(
    engine: Engine, events: Events
) -> None:
    apply(engine, events.created("V1", CODE_VALUE, "Discipline.PIP", scope=COMPANY))
    with pytest.raises(LookupError):
        apply(engine, close(events, "V1"))
    assert rows(engine, CODE_VALUE_TABLE) == []


def test_a_value_is_defined_once_per_scope_and_list(engine: Engine, events: Events) -> None:
    apply(engine, *define(events, "V1", "Discipline", "PIP"))
    with pytest.raises(IntegrityError):
        apply(engine, *define(events, "V2", "Discipline", "PIP"))
    apply(engine, *define(events, "V3", "Discipline", "PIP", scope=PROJECT, origin="project"))
    apply(engine, *define(events, "V4", "Craft", "PIP"))
    assert [r["id"] for r in rows(engine, CODE_VALUE_TABLE)] == ["V1", "V3", "V4"]


def test_reset_empties_the_table_and_a_replay_gives_the_same_rows(
    engine: Engine, events: Events
) -> None:
    stream = [
        *define(events, "V1", "Discipline", "PIP", sort_order=2, attributes={"a": 1}),
        *define(events, "V2", "Discipline", "ELE", sort_order=1),
        close(events, "V1", lifecycle="superseded", superseded_by="V2"),
    ]
    apply(engine, *stream)
    first = rows(engine, CODE_VALUE_TABLE)
    projector = CodeValueProjector()
    with engine.begin() as conn:
        projector.reset(conn)
    assert rows(engine, CODE_VALUE_TABLE) == []
    with engine.begin() as conn:
        for event in stream:
            if event.event_type in projector.handles:
                projector.apply(conn, event)
    assert rows(engine, CODE_VALUE_TABLE) == first


def test_an_event_it_does_not_handle_is_refused(engine: Engine, events: Events) -> None:
    other = events.make("Tag.Defined", {}, stream_id="V1", stream_type=CODE_VALUE)
    with engine.begin() as conn, pytest.raises(ValueError, match="cannot apply"):
        CodeValueProjector().apply(conn, other)
