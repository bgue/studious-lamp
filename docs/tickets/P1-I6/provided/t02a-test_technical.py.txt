"""Raise, edit, submit and return a Technical item: the raiser's side (P1-I6-T02a).

The item is a Draft numbered by kind, with the domain's data in its own table and the register
text (the question, the date an answer is needed) in the item table. Every refusal happens before
anything is written.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_correspondence.errors import (
    CorrespondenceScopeError,
    InvalidItemError,
    ItemStateError,
    UnknownDomainError,
)
from tl_mod_correspondence.testing import CorrWorld, frozen_today

MONDAY = "2026-10-19"
FUTURE = "2026-11-30"


def count_events(world: CorrWorld) -> int:
    return world.scalar("SELECT count(*) FROM events")


def names(world: CorrWorld, stream_id: str) -> list[str]:
    return [n for n, _ in world.events_of(stream_id)]


def payload(world: CorrWorld, stream_id: str, name: str) -> dict[str, Any]:
    [found] = [p for n, p in world.events_of(stream_id) if n == name]
    return found


# --- RaiseTechnical -------------------------------------------------------------------------


def test_an_rfi_is_a_draft_numbered_by_kind_with_its_data_and_its_register_text(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(
            proposed_solution="Move the beam 200 mm east.",
            discipline="structural",
            required_by=FUTURE,
            potential_cost_impact="yes",
            potential_schedule_impact="no",
            cc=[{"name": "Site office", "email": "site@meridian.example"}],
        )
    assert made.key == "P123-RFI-0001" and made.version >= 1
    assert names(world, made.stream_id)[:3] == [
        "Record.Created",
        "Correspondence.Defined",
        "Technical.Defined",
    ]
    row = world.technical("P123-RFI-0001")
    item, data = row.item, row.data
    assert (item.state, item.direction, item.domain, item.subtype) == (
        "Draft",
        "out",
        "technical",
        "rfi",
    )
    assert item.confidentiality == "internal" and item.response_required is True
    assert item.subject == "Beam B12 clashes with line 47"
    assert item.body == "The isometric clashes with beam B12; confirm the routing."
    assert item.response_due == FUTURE  # the register shows the date an answer is needed
    assert [r["name"] for r in item.to] == ["Meridian Energy"]
    assert [r["name"] for r in item.cc] == ["Site office"]
    assert data.question == item.body
    assert data.proposed_solution == "Move the beam 200 mm east."
    assert (data.discipline, data.required_by) == ("structural", FUTURE)
    assert (data.potential_cost_impact, data.potential_schedule_impact) == ("yes", "no")
    assert data.answer is None and data.answered_on is None


def test_the_flags_default_to_unknown_and_an_optional_field_may_be_left_out(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=None, to=[])
    row = world.technical(made.key or "")
    assert (row.data.potential_cost_impact, row.data.potential_schedule_impact) == (
        "unknown",
        "unknown",
    )
    assert (row.data.required_by, row.data.proposed_solution, row.data.discipline) == (
        None,
        None,
        None,
    )
    assert row.item.response_due is None and row.item.to == []


def test_each_subtype_counts_on_its_own(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        numbers = [
            world.raise_technical(subtype=s).key for s in ("rfi", "tq", "rfi", "deviation", "tq")
        ]
    assert numbers == [
        "P123-RFI-0001",
        "P123-TQ-0001",
        "P123-RFI-0002",
        "P123-DEV-0001",
        "P123-TQ-0002",
    ]
    assert world.technical("P123-DEV-0001").item.subtype == "deviation"


def test_the_item_is_in_the_technical_workflow_and_belongs_to_the_technical_record_type(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical()
    assert world.item("P123-RFI-0001").record_type == "correspondence.TechnicalItem"
    assert world.technical("P123-RFI-0001").item.id == made.stream_id


def test_the_references_become_links_of_the_raiser(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.forge_item("P123-COR-0001", subject="Client letter", state="Received")
        second = world.forge_item("P123-COR-0002", subject="Drawing note", state="Received")
        made = world.raise_technical(
            references=[
                {"record_id": first, "note": "the letter"},
                {"record_id": second, "pin": "B"},
            ]
        )
    links = world.rows(
        "SELECT to_id, relation, source, note, pin FROM cur_links WHERE from_id = :f "
        "ORDER BY to_id",
        f=made.stream_id,
    )
    assert [(r["to_id"], r["relation"], r["source"]) for r in links] == sorted(
        [(first, "references", "manual"), (second, "references", "manual")]
    )
    assert {r["to_id"]: (r["note"], r["pin"]) for r in links} == {
        first: ("the letter", None),
        second: (None, "B"),
    }
    assert sum(1 for n in names(world, made.stream_id) if n.startswith("Link.")) == 0
    assert len([e for e in made.events if e.event_type.startswith("Link.")]) == 2


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"subtype": "letter"}, UnknownDomainError),
        ({"subtype": "nonsense"}, UnknownDomainError),
        ({"required_by": "2026-10-18"}, InvalidItemError),
        ({"required_by": "2026-02-30"}, InvalidItemError),
        ({"required_by": "next week"}, InvalidItemError),
        ({"potential_cost_impact": "maybe"}, ValidationError),
        ({"potential_schedule_impact": "YES"}, ValidationError),
        ({"subject": "   "}, ValidationError),
        ({"question": ""}, ValidationError),
        ({"question": "  \n "}, ValidationError),
        ({"surprise": "x"}, ValidationError),
        ({"to": [{"name": "A", "email": "not-an-address"}]}, ValidationError),
    ],
)
def test_a_raise_that_cannot_be_used_writes_nothing(
    world: CorrWorld, fields: dict[str, Any], error: type[Exception]
) -> None:
    before = count_events(world)
    with frozen_today(MONDAY), pytest.raises(error):
        world.raise_technical(**fields)
    assert count_events(world) == before


def test_a_reference_that_is_unknown_foreign_or_repeated_is_refused_before_any_write(
    world: CorrWorld,
) -> None:
    known = world.forge_item("P123-COR-0001", state="Received")
    foreign = world.forge_technical("P123-RFI-0050", scope="project:OTHER")
    before = count_events(world)
    with frozen_today(MONDAY):
        for refs, error in (
            ([{"record_id": "01J000000000000000000000"}], RecordNotFoundError),
            ([{"record_id": foreign}], RecordNotFoundError),
            ([{"record_id": known}, {"record_id": known}], InvalidItemError),
        ):
            with pytest.raises(error):
                world.raise_technical(references=refs)
    assert count_events(world) == before


def test_a_reference_the_raiser_may_not_read_is_the_same_unknown_record(world: CorrWorld) -> None:
    secret = world.forge_item(
        "P123-COR-0003", subject="Counsel advice", state="Received", confidentiality="restricted"
    )
    with frozen_today(MONDAY):
        with pytest.raises(RecordNotFoundError) as hidden:
            world.raise_technical(references=[{"record_id": secret}])
        with pytest.raises(RecordNotFoundError) as unknown:
            world.raise_technical(references=[{"record_id": "01J000000000000000000001"}])
    assert str(hidden.value).replace(secret, "X") == str(unknown.value).replace(
        "01J000000000000000000001", "X"
    )


def test_a_raise_outside_a_project_scope_is_refused(world: CorrWorld) -> None:
    with frozen_today(MONDAY), pytest.raises(CorrespondenceScopeError):
        world.raise_technical(scope="company")


def test_the_required_by_date_may_be_today(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=MONDAY)
    assert world.technical(made.key or "").data.required_by == MONDAY


# --- UpdateTechnical ------------------------------------------------------------------------


def test_an_update_changes_the_given_fields_and_keeps_the_rest(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(proposed_solution="Move it.", discipline="piping")
        done = world.update_technical(
            made.stream_id,
            subject="Beam B12 clashes with line 48",
            question="Please confirm the new routing.",
            discipline="structural",
            potential_cost_impact="yes",
        )
    assert done.key == "P123-RFI-0001" and done.version > made.version
    assert [e.event_type for e in done.events] == [
        "Record.Updated",
        "Correspondence.Updated",
        "Technical.Updated",
    ]
    row = world.technical("P123-RFI-0001")
    assert row.item.subject == "Beam B12 clashes with line 48"
    assert row.item.body == "Please confirm the new routing."  # the register text follows
    assert row.data.question == "Please confirm the new routing."
    assert (row.data.discipline, row.data.proposed_solution) == ("structural", "Move it.")
    assert (row.data.potential_cost_impact, row.data.potential_schedule_impact) == (
        "yes",
        "unknown",
    )
    changes = payload(world, made.stream_id, "Technical.Updated")["changes"]
    assert set(changes) == {"question", "discipline", "potential_cost_impact"}
    assert changes["discipline"] == ["piping", "structural"]


def test_the_date_needed_follows_into_the_register_and_a_null_clears_the_optional_fields(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(
            required_by=FUTURE, proposed_solution="Move it.", discipline="piping"
        )
        world.update_technical(made.stream_id, required_by="2026-12-15")
        row = world.technical("P123-RFI-0001")
        assert (row.data.required_by, row.item.response_due) == ("2026-12-15",) * 2
        world.update_technical(
            made.stream_id, required_by=None, proposed_solution=None, discipline=None
        )
    row = world.technical("P123-RFI-0001")
    assert (row.data.required_by, row.item.response_due) == (None, None)
    assert (row.data.proposed_solution, row.data.discipline) == (None, None)


def test_recipients_are_replaced_as_a_list_and_a_list_may_be_emptied(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical()
        world.update_technical(
            made.stream_id,
            to=[{"name": "Designer", "email": "d@design.example"}],
            cc=[],
        )
    item = world.technical("P123-RFI-0001").item
    assert [r["name"] for r in item.to] == ["Designer"] and item.cc == []
    with frozen_today(MONDAY), pytest.raises(InvalidItemError, match="send \\[\\] to clear"):
        world.update_technical(made.stream_id, to=None)


def test_the_question_and_the_flags_cannot_be_cleared(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical()
        before = count_events(world)
        for field in ("question", "potential_cost_impact", "potential_schedule_impact"):
            with pytest.raises(InvalidItemError, match="cannot be cleared"):
                world.update_technical(made.stream_id, **{field: None})
        with pytest.raises(InvalidItemError):
            world.update_technical(made.stream_id, required_by="2026-10-01")
        with pytest.raises(ValidationError):
            world.update_technical(made.stream_id, potential_cost_impact="soon")
    assert count_events(world) == before


def test_an_update_that_changes_nothing_is_refused(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(discipline="piping")
        with pytest.raises(NoChangesError):
            world.update_technical(made.stream_id, discipline="piping")
        with pytest.raises(NoChangesError):
            world.update_technical(made.stream_id, subject="Beam B12 clashes with line 47")
        with pytest.raises(NoChangesError):
            world.update_technical(made.stream_id)


def test_the_reason_is_recorded_with_the_domain_change(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical()
        world.update_technical(made.stream_id, discipline="piping", reason="wrong trade")
    assert payload(world, made.stream_id, "Technical.Updated")["reason"] == "wrong trade"


def test_an_item_in_internal_review_may_be_changed_but_a_later_one_may_not(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=FUTURE)
        world.submit_technical(made.stream_id)
        world.update_technical(made.stream_id, discipline="piping", reason="review comment")
        assert world.technical("P123-RFI-0001").data.discipline == "piping"
    later = world.forge_technical("P123-RFI-0002", state="Awaiting response")
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.update_technical(later, discipline="structural")


@pytest.mark.parametrize("state", ["Issued", "Awaiting response", "Answered", "Accepted", "Closed"])
def test_no_state_after_review_takes_a_change(world: CorrWorld, state: str) -> None:
    number = "P123-RFI-0009"
    item_id = world.forge_technical(number, state=state)
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.update_technical(item_id, discipline="piping")


def test_an_update_on_a_stale_version_is_a_conflict(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical()
        world.update_technical(made.stream_id, discipline="piping")
        with pytest.raises(ConcurrencyError):
            world.update_technical(
                made.stream_id, discipline="steel", expected_version=made.version
            )


def test_an_update_of_something_that_is_not_a_readable_technical_item_is_not_found(
    world: CorrWorld,
) -> None:
    letter = world.forge_item("P123-COR-0001", state="Received")
    foreign = world.forge_technical("P123-RFI-0005", scope="project:OTHER")
    restricted = world.forge_technical("P123-RFI-0006", confidentiality="restricted")
    with frozen_today(MONDAY):
        for target in (letter, foreign, restricted, "01J000000000000000000000"):
            with pytest.raises(RecordNotFoundError):
                world.update_technical(target, discipline="piping")


# --- SubmitTechnical ------------------------------------------------------------------------


def test_a_draft_with_a_recipient_and_a_date_goes_to_internal_review(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=FUTURE)
        done = world.submit_technical(made.stream_id)
    assert world.technical("P123-RFI-0001").item.state == "Internal review"
    assert done.version > made.version and done.key == "P123-RFI-0001"
    assert any(e.event_type == "Workflow.Transitioned" for e in done.events)


def test_a_draft_without_a_recipient_or_a_date_cannot_be_submitted(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        nobody = world.raise_technical(to=[])
        undated = world.raise_technical(required_by=None)
        neither = world.raise_technical(to=[], required_by=None)
        with pytest.raises(InvalidItemError, match="needs a recipient before review"):
            world.submit_technical(nobody.stream_id)
        with pytest.raises(InvalidItemError, match="needs required_by before review"):
            world.submit_technical(undated.stream_id)
        with pytest.raises(InvalidItemError, match="a recipient and required_by"):
            world.submit_technical(neither.stream_id)
    for key in (nobody.key, undated.key, neither.key):
        assert world.technical(key or "").item.state == "Draft"


def test_a_date_that_has_passed_by_the_time_of_submission_is_refused(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by="2026-10-20")
    with frozen_today("2026-10-21"), pytest.raises(InvalidItemError, match="before today"):
        world.submit_technical(made.stream_id)
    with frozen_today("2026-10-20"):
        world.submit_technical(made.stream_id)  # on the day itself it is still fine


def test_only_a_draft_can_be_submitted(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=FUTURE)
        world.submit_technical(made.stream_id)
        with pytest.raises(ItemStateError):
            world.submit_technical(made.stream_id)
    waiting = world.forge_technical("P123-RFI-0007", state="Awaiting response")
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.submit_technical(waiting)


def test_submitting_an_unreadable_or_unknown_item_is_not_found(world: CorrWorld) -> None:
    hidden = world.forge_technical("P123-RFI-0006", confidentiality="restricted")
    with frozen_today(MONDAY):
        for target in (hidden, "01J000000000000000000000"):
            with pytest.raises(RecordNotFoundError):
                world.submit_technical(target)


# --- ReturnTechnical ------------------------------------------------------------------------


def test_an_item_in_review_goes_back_to_draft_with_the_reason(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=FUTURE)
        world.submit_technical(made.stream_id)
        done = world.return_technical(made.stream_id, reason="state the clash clearly")
        assert world.technical("P123-RFI-0001").item.state == "Draft"
        transitions = [
            p for n, p in world.events_of(made.stream_id) if n == "Workflow.Transitioned"
        ]
        assert transitions[-1]["reason"] == "state the clash clearly"
        assert done.version > made.version
        world.update_technical(made.stream_id, discipline="piping")  # a Draft again
        world.submit_technical(made.stream_id)
        assert world.technical("P123-RFI-0001").item.state == "Internal review"


def test_a_return_needs_a_reason_and_an_item_in_review(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=FUTURE)
        with pytest.raises(ItemStateError):  # still a Draft
            world.return_technical(made.stream_id, reason="not yet")
        world.submit_technical(made.stream_id)
        for blank in ("", "   "):
            with pytest.raises(ValidationError):
                world.return_technical(made.stream_id, reason=blank)
    issued = world.forge_technical("P123-RFI-0008", state="Awaiting response")
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.return_technical(issued, reason="too late")
    assert world.technical("P123-RFI-0001").item.state == "Internal review"


def test_returning_an_unreadable_or_unknown_item_is_not_found(world: CorrWorld) -> None:
    hidden = world.forge_technical(
        "P123-RFI-0006", state="Internal review", confidentiality="restricted"
    )
    with frozen_today(MONDAY):
        for target in (hidden, "01J000000000000000000000"):
            with pytest.raises(RecordNotFoundError):
                world.return_technical(target, reason="x")


def test_a_recipient_that_names_a_party_needs_a_party_of_the_project(world: CorrWorld) -> None:
    party = world.forge_party("MER", "Meridian Energy")
    with frozen_today(MONDAY):
        made = world.raise_technical(to=[{"name": "Meridian", "party_id": party}])
        world.update_technical(made.stream_id, cc=[{"party_id": party}])
        before = count_events(world)
        for field in ("to", "cc"):
            with pytest.raises(InvalidItemError, match="is not a party of"):
                world.update_technical(made.stream_id, **{field: [{"party_id": "NOSUCH"}]})
        with pytest.raises(InvalidItemError, match="is not a party of"):
            world.raise_technical(to=[{"party_id": "NOSUCH"}])
    assert count_events(world) == before


def test_a_transition_on_a_stale_version_is_a_conflict(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=FUTURE)
        world.update_technical(made.stream_id, discipline="piping")  # the item moved on
        with pytest.raises(ConcurrencyError):
            world.submit_technical(made.stream_id, expected_version=made.version)
        world.submit_technical(made.stream_id)
        stale = world.technical("P123-RFI-0001").item.version - 1
        with pytest.raises(ConcurrencyError):
            world.return_technical(made.stream_id, expected_version=stale)
        world.return_technical(
            made.stream_id, expected_version=world.technical("P123-RFI-0001").item.version
        )
