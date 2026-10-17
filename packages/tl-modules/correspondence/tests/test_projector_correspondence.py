"""CorrespondenceProjector: each item event into the item and clearance tables (P1-I5-T03a)."""

from __future__ import annotations

from typing import Any

from corrworld import Events, apply, as_json, install, table_rows
from sqlalchemy import Engine
from tl_core.projection.defaults import default_registry

ITEM = "ITEM1"
OTHER = "ITEM2"
ITEM_TABLE = "cur_correspondence_correspondence"
CLEARANCE_TABLE = "cur_correspondence_clearance"
TYPE = "correspondence.Correspondence"


def defined(events: Events, stream: str, number: str, **more: Any) -> list[Any]:
    payload: dict[str, Any] = {
        "number": number,
        "direction": "in",
        "medium": "letter",
        "received_via": "upload",
        "to": [{"name": "Project manager", "email": None, "party_id": None}],
        "cc": [],
        "confidentiality": "internal",
        **more,
    }
    return [
        events.created(stream, TYPE, number, title="Revised programme"),
        events.make("Correspondence.Defined", payload, stream_id=stream, stream_type=TYPE),
    ]


def journal(events: Events) -> list[Any]:
    """An incoming letter that is triaged, threaded, answered and reclassified; an outgoing one."""
    out = defined(
        events,
        ITEM,
        "P123-COR-0001",
        external_ref="MER/L/0042",
        from_name="Meridian Energy",
        sent_on="2026-10-16",
        received_on="2026-10-17",
        body="Please confirm the revised programme.",
        response_required=True,
        response_due="2026-10-31",
    )
    out += [
        events.make(
            "Correspondence.Triaged",
            {
                "domain": "general",
                "subtype": "letter",
                "referenced_ids": [],
                "clock_ids": [],
                "triaged_on": "2026-10-17",
            },
            stream_id=ITEM,
            stream_type=TYPE,
            actor="user:amy",
        ),
        events.make(
            "Correspondence.ThreadAssigned",
            {"thread_id": "THR1", "matched_by": "header", "responds_to_id": OTHER},
            stream_id=ITEM,
            stream_type=TYPE,
        ),
        events.make(
            "Correspondence.Updated",
            {
                "changes": {
                    "body": ["Please confirm the revised programme.", "Please confirm."],
                    "response_due": ["2026-10-31", "2026-11-03"],
                    "cc": [[], [{"name": "Site office", "email": None, "party_id": None}]],
                }
            },
            stream_id=ITEM,
            stream_type=TYPE,
        ),
        events.make(
            "Correspondence.Responded",
            {"response_id": OTHER, "responded_on": "2026-10-20"},
            stream_id=ITEM,
            stream_type=TYPE,
        ),
        events.make(
            "Correspondence.Reclassified",
            {"domain": "document_control", "subtype": "submittal", "reason": "Transmits drawings"},
            stream_id=ITEM,
            stream_type=TYPE,
        ),
        events.make(
            "Correspondence.Superseded",
            {"superseded_by_id": "ITEM3", "reason": "Corrected figures"},
            stream_id=ITEM,
            stream_type=TYPE,
        ),
    ]
    out += defined(events, OTHER, "P123-COR-0002", direction="out", medium="email")
    out += [
        events.make(
            "Correspondence.Issued",
            {
                "issued_on": "2026-10-20",
                "rendition_file_id": "F1",
                "rendition_sha256": "ab" * 32,
                "template": "general-letter",
                "delivery": "stub",
                "clock_ids": [],
            },
            stream_id=OTHER,
            stream_type=TYPE,
        ),
        events.make(
            "Correspondence.ConfidentialityChanged",
            {"from_class": "internal", "to_class": "privileged", "reason": "Legal advice"},
            stream_id=OTHER,
            stream_type=TYPE,
        ),
        events.make(
            "Correspondence.ClearanceGranted",
            {"account": "user:amy", "granted_on": "2026-10-21", "reason": "Counsel"},
            stream_id=OTHER,
            stream_type=TYPE,
            actor="user:ctl",
        ),
        events.make(
            "Correspondence.ClearanceGranted",
            {"account": "user:bo", "granted_on": "2026-10-21", "reason": "Counsel"},
            stream_id=OTHER,
            stream_type=TYPE,
            actor="user:ctl",
        ),
        events.make(
            "Correspondence.ClearanceWithdrawn",
            {"account": "user:bo", "reason": "Matter closed"},
            stream_id=OTHER,
            stream_type=TYPE,
        ),
    ]
    return out


def snapshot(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    return {
        ITEM_TABLE: table_rows(engine, ITEM_TABLE),
        CLEARANCE_TABLE: table_rows(engine, CLEARANCE_TABLE, "clearance_id"),
    }


def test_the_whole_journal_projects_and_a_second_database_gets_the_same_rows(
    engine: Engine, new_engine: Any, dialect: str
) -> None:
    events = journal(Events())
    apply(engine, *events)
    first = snapshot(engine)
    other = new_engine()
    install(other, dialect)
    apply(other, *events)
    assert snapshot(other) == first
    other.dispose()


def test_a_defined_item_has_the_fields_of_its_event(engine: Engine) -> None:
    events = Events()
    apply(
        engine,
        *defined(
            events,
            ITEM,
            "P123-COR-0001",
            external_ref="MER/L/0042",
            message_id="abc@mail.example",
            in_reply_to="prev@mail.example",
            from_party_id="PARTY1",
            from_name="Meridian Energy",
            sent_on="2026-10-16",
            received_on="2026-10-17",
            body="Hello",
            confidentiality="restricted",
            response_required=True,
            response_due="2026-10-31",
        ),
    )
    (row,) = table_rows(engine, ITEM_TABLE)
    assert row["id"] == ITEM and row["scope"] == "project:P123"
    assert row["number"] == "P123-COR-0001"
    assert row["direction"] == "in" and row["medium"] == "letter"
    assert row["received_via"] == "upload"
    assert row["external_ref"] == "MER/L/0042" and row["message_id"] == "abc@mail.example"
    assert row["in_reply_to"] == "prev@mail.example" and row["from_party_id"] == "PARTY1"
    assert row["from_name"] == "Meridian Energy"
    assert row["sent_on"] == "2026-10-16" and row["received_on"] == "2026-10-17"
    assert row["body"] == "Hello" and row["confidentiality"] == "restricted"
    assert bool(row["response_required"]) is True and row["response_due"] == "2026-10-31"
    assert as_json(row["to_parties_json"]) == [
        {"name": "Project manager", "email": None, "party_id": None}
    ]
    assert as_json(row["cc_parties_json"]) == []
    assert row["domain"] is None and row["subtype"] is None  # not triaged yet
    assert row["thread_id"] is None and row["issued_on"] is None
    assert row["delivery"] == "none" and row["last_seq"] == 2


def test_an_item_with_only_the_required_fields_gets_the_defaults(engine: Engine) -> None:
    apply(engine, *defined(Events(), ITEM, "P123-COR-0003"))
    (row,) = table_rows(engine, ITEM_TABLE)
    assert bool(row["response_required"]) is False and row["response_due"] is None
    assert row["body"] is None and row["external_ref"] is None
    assert row["confidentiality"] == "internal"


def test_triage_sets_domain_subtype_date_and_the_actor(engine: Engine) -> None:
    apply(engine, *journal(Events())[:3])
    (row,) = table_rows(engine, ITEM_TABLE)
    assert row["domain"] == "general" and row["subtype"] == "letter"
    assert row["triaged_on"] == "2026-10-17" and row["triaged_by"] == "user:amy"


def test_the_events_after_triage_land_on_the_item_row(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    first, second = table_rows(engine, ITEM_TABLE)
    assert first["number"] == "P123-COR-0001"
    assert first["thread_id"] == "THR1" and first["responds_to_id"] == OTHER
    assert first["responded_on"] == "2026-10-20"
    assert first["domain"] == "document_control" and first["subtype"] == "submittal"  # reclassified
    assert first["superseded_by_id"] == "ITEM3"
    assert first["body"] == "Please confirm." and first["response_due"] == "2026-11-03"
    assert as_json(first["cc_parties_json"]) == [
        {"name": "Site office", "email": None, "party_id": None}
    ]
    assert as_json(first["to_parties_json"]) == [
        {"name": "Project manager", "email": None, "party_id": None}
    ]  # not in the update
    assert first["from_name"] == "Meridian Energy"  # untouched
    assert second["issued_on"] == "2026-10-20" and second["rendition_file_id"] == "F1"
    assert second["rendition_sha256"] == "ab" * 32 and second["delivery"] == "stub"
    assert second["confidentiality"] == "privileged"


def test_a_thread_assignment_without_a_parent_keeps_the_one_the_item_had(engine: Engine) -> None:
    events = Events()
    apply(
        engine,
        *defined(events, ITEM, "P123-COR-0001", responds_to_id=OTHER),
        events.make(
            "Correspondence.ThreadAssigned",
            {"thread_id": "THR1", "matched_by": "subject"},
            stream_id=ITEM,
            stream_type=TYPE,
        ),
    )
    (row,) = table_rows(engine, ITEM_TABLE)
    assert row["thread_id"] == "THR1" and row["responds_to_id"] == OTHER


def test_clearance_rows_follow_grants_and_withdrawals(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    (row,) = table_rows(engine, CLEARANCE_TABLE, "clearance_id")
    assert row["clearance_id"] == f"{OTHER}:user:amy"
    assert row["record_id"] == OTHER and row["account"] == "user:amy"
    assert row["granted_by"] == "user:ctl" and row["granted_on"] == "2026-10-21"
    assert row["scope"] == "project:P123"


def test_a_withdrawn_clearance_can_be_granted_again(engine: Engine) -> None:
    events = Events()
    grant = {"account": "user:amy", "granted_on": "2026-10-21", "reason": "Counsel"}
    apply(
        engine,
        *defined(events, ITEM, "P123-COR-0001", confidentiality="privileged"),
        events.make("Correspondence.ClearanceGranted", grant, stream_id=ITEM, stream_type=TYPE),
        events.make(
            "Correspondence.ClearanceWithdrawn",
            {"account": "user:amy", "reason": "x"},
            stream_id=ITEM,
            stream_type=TYPE,
        ),
        events.make("Correspondence.ClearanceGranted", grant, stream_id=ITEM, stream_type=TYPE),
    )
    assert len(table_rows(engine, CLEARANCE_TABLE, "clearance_id")) == 1


def test_every_event_moves_the_envelope_version(engine: Engine) -> None:
    events = journal(Events())
    apply(engine, *events)
    with engine.connect() as conn:
        found = conn.exec_driver_sql(
            "SELECT id, version, last_seq FROM cur_core_record ORDER BY id"
        ).all()
    versions = {row[0]: (row[1], row[2]) for row in found}
    assert versions[ITEM][0] == 8  # Created + Defined + six more
    assert versions[OTHER][0] == 7


def test_an_event_for_an_item_that_was_never_defined_is_an_error(engine: Engine) -> None:
    import pytest

    events = Events()
    with pytest.raises(LookupError):
        apply(
            engine,
            events.created(ITEM, TYPE, "P123-COR-0001"),
            events.make(
                "Correspondence.Responded",
                {"response_id": OTHER, "responded_on": "2026-10-20"},
                stream_id=ITEM,
                stream_type=TYPE,
            ),
        )


def test_the_projector_is_registered_and_resets_its_tables(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    registry = default_registry()
    (projector,) = [
        p for p in registry.for_event("Correspondence.Defined") if p.name == "correspondence_item"
    ]
    with engine.begin() as conn:
        projector.reset(conn)
    assert table_rows(engine, ITEM_TABLE) == []
    assert table_rows(engine, CLEARANCE_TABLE, "clearance_id") == []
