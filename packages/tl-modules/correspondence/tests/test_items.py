"""Receive an item and change its register fields (P1-I5-T07a)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_core import confidentiality as cf
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_correspondence.errors import CorrespondenceScopeError, InvalidItemError, ItemStateError
from tl_mod_correspondence.testing import BASE, CorrWorld, frozen_today

MONDAY = "2026-10-19"


def events(world: CorrWorld, item_id: str) -> list[str]:
    return [name for name, _ in world.events_of(item_id)]


def test_a_received_item_is_numbered_starts_received_and_is_internal(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive(external_ref="MER/L/0042", sent_on="2026-10-16")
    assert made.key == "P123-COR-0001"
    assert events(world, made.stream_id)[:3] == [
        "Record.Created",
        "Correspondence.Defined",
        "Workflow.Transitioned",
    ]
    item = world.item("P123-COR-0001")
    assert (item.state, item.direction, item.medium, item.received_via) == (
        "Received",
        "in",
        "letter",
        "manual",
    )
    assert (item.confidentiality, item.delivery, item.domain, item.subtype) == (
        "internal",
        "none",
        None,
        None,
    )
    assert (item.subject, item.external_ref, item.sent_on, item.received_on) == (
        "Revised programme",
        "MER/L/0042",
        "2026-10-16",
        MONDAY,
    )
    assert item.body == "Please confirm the revised programme."
    second = world.receive("Another letter")
    assert second.key == "P123-COR-0002"


def test_the_defined_event_carries_every_field_the_projector_needs(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive(
            to=[{"name": "Project manager"}],
            cc=[{"email": "Site@Example.COM"}],
            response_required=True,
            response_due="2026-11-02",
            medium="email",
            received_via="email",
            in_reply_to="<abc@mail.example>",
            message_id="<xyz@mail.example>",
        )
    payload = world.events_of(made.stream_id)[1][1]
    assert payload["number"] == "P123-COR-0001"
    assert payload["direction"] == "in" and payload["confidentiality"] == "internal"
    assert payload["to"] == [{"name": "Project manager", "email": None, "party_id": None}]
    assert payload["cc"] == [{"name": None, "email": "site@example.com", "party_id": None}]
    assert payload["message_id"] == "xyz@mail.example"  # stored without the angle brackets
    assert payload["in_reply_to"] == "abc@mail.example"
    assert (payload["response_required"], payload["response_due"]) == (True, "2026-11-02")
    assert payload["received_on"] == MONDAY and payload["sent_on"] is None
    item = world.item("P123-COR-0001")
    assert item.cc == [{"name": None, "email": "site@example.com", "party_id": None}]
    assert item.response_required is True


def test_received_on_defaults_to_today_and_is_never_after_today(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        world.receive()
        assert world.item("P123-COR-0001").received_on == MONDAY
        with pytest.raises(InvalidItemError):
            world.receive(received_on="2026-10-20")
        world.receive(received_on="2026-10-12")
    assert world.item("P123-COR-0002").received_on == "2026-10-12"


def test_a_bad_date_party_or_text_is_refused_before_anything_is_written(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        refused: list[dict[str, Any]] = [
            {"sent_on": "16/10/2026"},
            {"sent_on": "2090-01-01"},
            {"response_due": "2026-02-30"},
            {"from_party_id": "01J000000000000000000000"},
            {"to": [{"party_id": "01J000000000000000000000"}]},
            {"body": "line\x07bell"},
        ]
        for more in refused:
            with pytest.raises(InvalidItemError):
                world.receive(**more)
        malformed: list[dict[str, Any]] = [
            {"subject": "  "},
            {"subject": "two\nlines"},
            {"subject": "x" * 501},
            {"from_name": "a‮b"},
            {"to": [{}]},
            {"to": [{"email": "not an email"}]},
            {"medium": "carrier pigeon"},
            {"received_via": "telepathy"},
            {"unknown_field": 1},
            {"cc": [{"name": "x"}] * 101},
        ]
        for more in malformed:
            with pytest.raises(ValidationError):
                world.receive(**more)
    assert world.rows("SELECT id FROM cur_core_record WHERE type LIKE 'correspondence.%'") == []


def test_a_known_party_can_be_named_and_a_message_id_is_received_once(world: CorrWorld) -> None:
    party = world.forge_party()
    with frozen_today(MONDAY):
        made = world.receive(from_party_id=party, message_id="<one@mail.example>")
        assert world.item(made.key or "").from_party_id == party
        with pytest.raises(InvalidItemError, match="already item P123-COR-0001"):
            world.receive(message_id="one@mail.example")
        with pytest.raises(InvalidItemError):
            world.receive(message_id="not a message id")


def test_an_item_needs_a_project(world: CorrWorld) -> None:
    with pytest.raises(CorrespondenceScopeError), frozen_today(MONDAY):
        world.receive(scope="company")


def test_an_item_is_numbered_per_project(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive()
        other = world.receive(scope="project:P999")
    assert (first.key, other.key) == ("P123-COR-0001", "P999-COR-0001")


def test_update_changes_the_subject_and_the_register_fields(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive(external_ref="OLD")
        done = world.update(
            made.stream_id,
            subject="Revised programme rev B",
            external_ref="NEW",
            body="Corrected text",
            response_required=True,
            to=[{"name": "PM"}],
            reason="typo",
        )
    assert [e.event_type for e in done.events] == ["Record.Updated", "Correspondence.Updated"]
    item = world.item("P123-COR-0001")
    assert (item.subject, item.external_ref, item.body, item.response_required) == (
        "Revised programme rev B",
        "NEW",
        "Corrected text",
        True,
    )
    assert item.to == [{"name": "PM", "email": None, "party_id": None}]
    envelope, register = world.events_of(made.stream_id)[-2:]
    assert envelope[1]["changes"] == {"title": ["Revised programme", "Revised programme rev B"]}
    assert register[1]["changes"]["external_ref"] == ["OLD", "NEW"]
    assert register[1]["reason"] == "typo"
    assert "subject" not in register[1]["changes"]


def test_update_leaves_out_fields_alone_and_null_clears_an_optional_one(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive(external_ref="REF", sent_on="2026-10-16")
        world.update(made.stream_id, sent_on=None)
    item = world.item("P123-COR-0001")
    assert (item.sent_on, item.external_ref) == (None, "REF")


def test_update_refuses_what_changes_nothing_or_cannot_be_cleared(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive(external_ref="REF")
        with pytest.raises(NoChangesError):
            world.update(made.stream_id, external_ref="REF")
        with pytest.raises(NoChangesError):
            world.update(made.stream_id)
        for more in ({"medium": None}, {"response_required": None}, {"to": None}):
            with pytest.raises(InvalidItemError):
                world.update(made.stream_id, **more)
        for more in (
            {"sent_on": "tomorrow"},
            {"received_on": "2026-10-20"},
            {"from_party_id": "01J000000000000000000000"},
            {"body": "x\x07y"},
        ):
            with pytest.raises(InvalidItemError):
                world.update(made.stream_id, **more)
        for more in ({"subject": ""}, {"subject": "a b"}, {"number": "X"}):
            with pytest.raises(ValidationError):
                world.update(made.stream_id, **more)


def test_update_takes_a_draft_and_a_received_item_but_not_a_triaged_one(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft()
        world.update(draft.stream_id, body="second thoughts")
        triaged = world.forge_item("P123-COR-0099", state="Triaged")
        with pytest.raises(ItemStateError):
            world.update(triaged, body="too late")


def test_update_checks_the_version_when_given(world: CorrWorld) -> None:
    from tl_core.ledger import ConcurrencyError

    with frozen_today(MONDAY):
        made = world.receive()
        with pytest.raises(ConcurrencyError):
            world.update(made.stream_id, body="x", expected_version=1)
        world.update(made.stream_id, body="x", expected_version=made.version)


def test_an_unknown_foreign_or_hidden_item_is_not_found(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive()
        with pytest.raises(RecordNotFoundError):
            world.update("01J000000000000000000000", body="x")
        with pytest.raises(RecordNotFoundError):
            world.update(made.stream_id, body="x", scope="project:P999")
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.set_class(made.stream_id, "restricted")
        with pytest.raises(RecordNotFoundError):
            world.update(made.stream_id, body="x")


def test_a_command_with_an_extra_field_is_refused_whole(world: CorrWorld) -> None:
    from tl_mod_correspondence.handlers.items import ReceiveCorrespondence

    fields: dict[str, Any] = {**BASE, "subject": "x", "number": "P123-COR-9999"}
    with pytest.raises(ValidationError):
        ReceiveCorrespondence(**fields)


def test_an_item_that_was_replaced_takes_no_more_changes(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        old = world.forge_item("P123-COR-0010", state="Draft")
        new = world.forge_item("P123-COR-0011", state="Draft")
        world.forge_item_event(
            old, "Correspondence.Superseded", {"superseded_by_id": new, "reason": "corrected"}
        )
        with pytest.raises(ItemStateError, match="replaced"):
            world.update(old, body="more")
        world.update(new, body="fine")
