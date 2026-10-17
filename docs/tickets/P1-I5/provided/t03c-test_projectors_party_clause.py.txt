"""PartyProjector and ClauseProjector: party, contact and clause events into their tables (T03c)."""

from __future__ import annotations

from typing import Any

from corrworld import Events, apply, as_json, install, table_rows
from sqlalchemy import Engine

PARTY = "PTY1"
CLAUSE = "CLA1"
PARTY_TYPE = "correspondence.Party"
CLAUSE_TYPE = "correspondence.ContractClause"
PARTY_TABLE = "cur_correspondence_party"
CONTACT_TABLE = "cur_correspondence_contact_role"
CLAUSE_TABLE = "cur_correspondence_contract_clause"


def party_events(events: Events) -> list[Any]:
    return [
        events.created(PARTY, PARTY_TYPE, "CLIENT", title="Meridian Energy"),
        events.make(
            "Party.Defined",
            {
                "code": "CLIENT",
                "project_role": "client",
                "email_domains": ["meridian.example"],
                "contacts": [
                    {
                        "name": "Dana Cole",
                        "email": "pm@meridian.example",
                        "title": "Project manager",
                        "domain": None,
                        "is_authorised": True,
                    },
                    {"name": "Lee Wong", "email": None, "title": None, "domain": "general"},
                ],
            },
            stream_id=PARTY,
            stream_type=PARTY_TYPE,
        ),
    ]


def clause_events(events: Events, **more: Any) -> list[Any]:
    payload: dict[str, Any] = {
        "contract": "MSA-2026",
        "clause_number": "20.1",
        "time_bar_days": 28,
        "time_bar_day_type": "calendar",
        "notice_requirements": "State the event and the date it was noticed",
        "required_recipients": ["project_manager"],
        "service_method": "letter",
        "domains": ["general"],
        **more,
    }
    return [
        events.created(CLAUSE, CLAUSE_TYPE, "MSA-2026/20.1", title="Notice of delay"),
        events.make("ContractClause.Defined", payload, stream_id=CLAUSE, stream_type=CLAUSE_TYPE),
    ]


def test_a_defined_party_has_its_code_role_domains_and_first_contacts(engine: Engine) -> None:
    apply(engine, *party_events(Events()))
    (party,) = table_rows(engine, PARTY_TABLE)
    assert party["id"] == PARTY and party["scope"] == "project:P123"
    assert party["code"] == "CLIENT" and party["project_role"] == "client"
    assert as_json(party["email_domains_json"]) == ["meridian.example"]
    assert bool(party["is_active"]) is True
    first, second = table_rows(engine, CONTACT_TABLE, "position")
    assert first["contact_id"] == f"{PARTY}:001" and first["party_id"] == PARTY
    assert first["position"] == 1 and first["name"] == "Dana Cole"
    assert first["email"] == "pm@meridian.example" and first["title"] == "Project manager"
    assert first["domain"] is None and bool(first["is_authorised"]) is True
    assert second["contact_id"] == f"{PARTY}:002" and second["position"] == 2
    assert second["email"] is None and second["domain"] == "general"
    assert bool(second["is_authorised"]) is False  # not stated: not authorised
    assert bool(second["is_active"]) is True and second["scope"] == "project:P123"


def test_a_contact_added_later_takes_the_position_the_event_states(engine: Engine) -> None:
    events = Events()
    apply(
        engine,
        *party_events(events),
        events.make(
            "Party.ContactAdded",
            {
                "position": 3,
                "name": "Sam Ray",
                "email": "sam@meridian.example",
                "title": "Planner",
                "domain": None,
                "is_authorised": False,
            },
            stream_id=PARTY,
            stream_type=PARTY_TYPE,
        ),
    )
    rows = table_rows(engine, CONTACT_TABLE, "position")
    assert [r["position"] for r in rows] == [1, 2, 3]
    assert rows[2]["contact_id"] == f"{PARTY}:003" and rows[2]["name"] == "Sam Ray"


def test_an_ended_contact_is_inactive_and_the_others_stay_active(engine: Engine) -> None:
    events = Events()
    apply(
        engine,
        *party_events(events),
        events.make(
            "Party.ContactEnded",
            {"position": 2, "reason": "Left the project"},
            stream_id=PARTY,
            stream_type=PARTY_TYPE,
        ),
    )
    first, second = table_rows(engine, CONTACT_TABLE, "position")
    assert bool(first["is_active"]) is True and bool(second["is_active"]) is False


def test_ending_a_contact_that_does_not_exist_is_an_error(engine: Engine) -> None:
    import pytest

    events = Events()
    with pytest.raises(LookupError):
        apply(
            engine,
            *party_events(events),
            events.make(
                "Party.ContactEnded",
                {"position": 9},
                stream_id=PARTY,
                stream_type=PARTY_TYPE,
            ),
        )


def test_a_retired_party_is_inactive_but_keeps_its_contacts(engine: Engine) -> None:
    events = Events()
    apply(
        engine,
        *party_events(events),
        events.make(
            "Party.Retired",
            {"reason": "Contract complete"},
            stream_id=PARTY,
            stream_type=PARTY_TYPE,
        ),
    )
    (party,) = table_rows(engine, PARTY_TABLE)
    assert bool(party["is_active"]) is False
    assert len(table_rows(engine, CONTACT_TABLE, "position")) == 2


def test_a_defined_clause_has_the_fields_of_its_event(engine: Engine) -> None:
    apply(engine, *clause_events(Events(), contract_document_id="DOC1"))
    (row,) = table_rows(engine, CLAUSE_TABLE)
    assert row["id"] == CLAUSE and row["scope"] == "project:P123"
    assert row["contract"] == "MSA-2026" and row["clause_number"] == "20.1"
    assert row["time_bar_days"] == 28 and row["time_bar_day_type"] == "calendar"
    assert row["notice_requirements"] == "State the event and the date it was noticed"
    assert as_json(row["required_recipients_json"]) == ["project_manager"]
    assert row["service_method"] == "letter" and row["contract_document_id"] == "DOC1"
    assert as_json(row["domains_json"]) == ["general"]
    assert bool(row["is_active"]) is True


def test_a_clause_without_a_time_bar_keeps_the_columns_null(engine: Engine) -> None:
    events = Events()
    created, defined = clause_events(events)
    for key in ("time_bar_days", "time_bar_day_type", "service_method"):
        del defined.payload[key]
    apply(engine, created, defined)
    (row,) = table_rows(engine, CLAUSE_TABLE)
    assert row["time_bar_days"] is None and row["time_bar_day_type"] is None
    assert row["service_method"] is None


def test_a_retired_clause_is_inactive(engine: Engine) -> None:
    events = Events()
    apply(
        engine,
        *clause_events(events),
        events.make(
            "ContractClause.Retired",
            {"reason": "Replaced"},
            stream_id=CLAUSE,
            stream_type=CLAUSE_TYPE,
        ),
    )
    (row,) = table_rows(engine, CLAUSE_TABLE)
    assert bool(row["is_active"]) is False


def test_the_same_events_give_the_same_rows_on_a_second_database(
    engine: Engine, new_engine: Any, dialect: str
) -> None:
    events = Events()
    journal = [*party_events(events), *clause_events(events)]
    apply(engine, *journal)
    other = new_engine()
    install(other, dialect)
    apply(other, *journal)
    for table, order in ((PARTY_TABLE, "id"), (CONTACT_TABLE, "contact_id"), (CLAUSE_TABLE, "id")):
        assert table_rows(other, table, order) == table_rows(engine, table, order)
    other.dispose()
