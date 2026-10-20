"""Raise, edit, submit, review and return a Commercial item (P1-I6-T04a).

A Commercial item is restricted and every command on it is a document controller's: the tests run
as a controller (`acting`) and one test shows the refusals for a plain viewer. The time bar of the
subtype starts when the item is made, counted from the day the contractor became aware.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.errors import (
    CorrespondenceScopeError,
    InvalidItemError,
    ItemStateError,
    UnknownDomainError,
)
from tl_mod_correspondence.handlers.commercial import RaiseCommercial, create_commercial
from tl_mod_correspondence.testing import BASE, CorrWorld, as_controller, frozen_today

MONDAY = "2026-10-19"


@contextmanager
def acting(day: str = MONDAY) -> Generator[None]:
    """A document controller on ``day``."""
    with frozen_today(day), as_controller():
        yield


def count_events(world: CorrWorld) -> int:
    return world.scalar("SELECT count(*) FROM events")


def names(world: CorrWorld, stream_id: str) -> list[str]:
    return [n for n, _ in world.events_of(stream_id)]


def payload(world: CorrWorld, stream_id: str, name: str) -> dict[str, Any]:
    [found] = [p for n, p in world.events_of(stream_id) if n == name]
    return found


# --- RaiseCommercial ------------------------------------------------------------------------


def test_an_early_warning_is_a_restricted_draft_with_its_figures(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial(
            currency="USD",
            estimated_value="12500",
            estimated_hours="240",
            cost_code_impacts=[
                {"cost_code": "2.3.1", "amount": "10000"},
                {"cost_code": "2.3.2", "amount": "2500.5", "hours": "100"},
            ],
            schedule_impact_days=3,
            schedule_impact_note="Spool S-14 is on the critical path.",
            entitlement_basis="Clause 20.1",
        )
        assert made.key == "P123-EW-0001"
        row = world.commercial("P123-EW-0001")
    item, data = row.item, row.data
    assert (item.state, item.direction, item.domain, item.subtype) == (
        "Draft",
        "out",
        "commercial",
        "early_warning",
    )
    assert item.confidentiality == "restricted" and item.response_required is True
    assert item.body == "The re-routing changes the scope of piping spool S-14."
    assert [r["name"] for r in item.to] == ["Meridian Energy"]
    with as_controller():
        assert world.item("P123-EW-0001").record_type == "correspondence.CommercialItem"
    assert (data.currency, data.estimated_value, data.estimated_hours) == (
        "USD",
        "12500.00",
        "240.0",
    )
    assert [(i["cost_code"], i["amount"], i["hours"]) for i in data.cost_code_impacts] == [
        ("2.3.1", "10000.00", None),
        ("2.3.2", "2500.50", "100.0"),
    ]
    assert data.schedule_impact_days == 3
    assert data.schedule_impact_note == "Spool S-14 is on the critical path."
    assert data.entitlement_basis == "Clause 20.1"
    assert (data.aware_on, data.derived_from_id, data.contract_clause_id) == (MONDAY, None, None)
    with acting():  # a day other than today is stored as given
        earlier = world.raise_commercial(aware_on="2026-10-12")
        assert world.commercial(earlier.key or "").data.aware_on == "2026-10-12"
    assert data.assessed_value is None and data.assessment_status is None
    assert names(world, made.stream_id)[:3] == [
        "Record.Created",
        "Correspondence.Defined",
        "Commercial.Defined",
    ]


def test_the_time_bar_starts_at_once_from_the_day_the_contractor_became_aware(
    world: CorrWorld,
) -> None:
    with acting():
        made = world.raise_commercial(aware_on="2026-10-12")
        [bar] = world.clocks("P123-EW-0001")  # the assessment clock starts when it is issued
    assert (bar.kind, bar.state, bar.start_on, bar.due_on) == (
        "time_bar",
        "running",
        "2026-10-12",
        "2026-10-26",
    )
    assert (bar.day_type, bar.duration_days, bar.clause_id, bar.label) == (
        "calendar",
        14,
        None,
        "Early warning time bar",
    )
    assert bar.warn_days == [7, 3, 1]
    assert sum(1 for e in made.events if e.event_type.startswith("ResponseClock.")) >= 1


def test_aware_on_defaults_to_today_may_be_today_and_may_not_be_later(world: CorrWorld) -> None:
    with acting():
        today_made = world.raise_commercial(aware_on=MONDAY)
        assert world.commercial(today_made.key or "").data.aware_on == MONDAY
        before = count_events(world)
        for bad in ("2026-10-20", "2026-02-30", "last week", "20261018"):
            with pytest.raises(InvalidItemError):
                world.raise_commercial(aware_on=bad)
    assert count_events(world) == before


def test_a_contract_clause_sets_the_length_of_the_bar_and_is_cited(world: CorrWorld) -> None:
    clause_id = world.forge_clause("CT-1", "20.1")  # 28 calendar days
    with acting():
        made = world.raise_commercial(clause="CT-1/20.1")
        row = world.commercial(made.key or "")
        [bar] = world.clocks(made.key or "")
    assert row.data.contract_clause_id == clause_id
    assert (bar.duration_days, bar.due_on, bar.clause_id) == (28, "2026-11-16", clause_id)


@pytest.mark.parametrize("clause", ["CT-1", "CT-1/99.9", "CT-9/20.1", "/20.1", "CT-1/"])
def test_a_clause_that_is_not_an_active_clause_of_the_scope_is_refused(
    world: CorrWorld, clause: str
) -> None:
    world.forge_clause("CT-1", "20.1")
    before = count_events(world)
    with acting(), pytest.raises(InvalidItemError, match="not an active contract clause"):
        world.raise_commercial(clause=clause)
    assert count_events(world) == before


def test_a_retired_clause_is_refused(world: CorrWorld) -> None:
    clause_id = world.forge_clause("CT-1", "20.1")
    with acting():
        world.retire_clause(clause_id)
        with pytest.raises(InvalidItemError, match="not an active contract clause"):
            world.raise_commercial(clause="CT-1/20.1")


def test_a_site_instruction_is_logged_and_waits_for_our_assessment(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial(
            "Site instruction 7: extra bracing", subtype="site_instruction", to=[]
        )
        row = world.commercial("P123-SI-0001")
        [bar] = world.clocks("P123-SI-0001")
    assert made.key == "P123-SI-0001"
    assert (row.item.state, row.item.direction, row.item.received_on) == (
        "Awaiting assessment",
        "in",
        MONDAY,
    )
    assert (bar.kind, bar.due_on) == ("time_bar", "2026-11-02")
    assert made.version == row.item.version


def test_every_subtype_has_its_own_number_and_counter(world: CorrWorld) -> None:
    with acting():
        numbers = [
            world.raise_commercial(subtype=s).key
            for s in (
                "early_warning",
                "change_notice",
                "quotation",
                "claim_notice",
                "detailed_claim",
                "payment_application",
                "back_charge",
                "early_warning",
            )
        ]
    assert numbers == [
        "P123-EW-0001",
        "P123-CN-0001",
        "P123-QT-0001",
        "P123-CL-0001",
        "P123-DC-0001",
        "P123-PA-0001",
        "P123-BC-0001",
        "P123-EW-0002",
    ]


def test_a_subtype_without_an_awareness_clock_starts_none(world: CorrWorld) -> None:
    with acting():
        world.raise_commercial(subtype="quotation")
        assert world.clocks("P123-QT-0001") == []


def test_the_references_become_links_of_the_controller(world: CorrWorld) -> None:
    rfi = world.forge_technical("P123-RFI-0001", state="Answered")
    with acting():
        made = world.raise_commercial(references=[{"record_id": rfi, "note": "the RFI"}])
    [link] = world.rows(
        "SELECT to_id, relation, source, note FROM cur_links WHERE from_id = :f", f=made.stream_id
    )
    assert (link["to_id"], link["relation"], link["source"], link["note"]) == (
        rfi,
        "references",
        "manual",
        "the RFI",
    )


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"subtype": "rfi"}, UnknownDomainError),
        ({"subtype": "nonsense"}, UnknownDomainError),
        ({"estimated_value": "12500"}, ValidationError),  # an amount needs a currency
        (
            {"cost_code_impacts": [{"cost_code": "2.3.1", "amount": "5"}]},
            ValidationError,
        ),
        ({"currency": "usd", "estimated_value": "1"}, ValidationError),
        ({"currency": "USD", "estimated_value": "12.345"}, ValidationError),
        ({"currency": "USD", "estimated_value": "1,000"}, ValidationError),
        ({"currency": "USD", "estimated_value": "-5"}, ValidationError),
        ({"currency": "USD", "estimated_value": "١٢"}, ValidationError),
        ({"currency": "USD", "estimated_value": "1e3"}, ValidationError),
        ({"currency": "USD", "estimated_hours": "1.25"}, ValidationError),
        ({"schedule_impact_days": 4000}, ValidationError),
        ({"subject": "  "}, ValidationError),
        ({"surprise": "x"}, ValidationError),
        (
            {
                "currency": "USD",
                "cost_code_impacts": [
                    {"cost_code": "2.3.1", "amount": "1"},
                    {"cost_code": "2.3.1", "amount": "2"},
                ],
            },
            InvalidItemError,
        ),
        ({"cost_code_impacts": [{"cost_code": "bad code!", "amount": "1"}]}, ValidationError),
    ],
)
def test_a_raise_that_cannot_be_used_writes_nothing(
    world: CorrWorld, fields: dict[str, Any], error: type[Exception]
) -> None:
    before = count_events(world)
    with acting(), pytest.raises(error):
        world.raise_commercial(**fields)
    assert count_events(world) == before


def test_a_reference_that_is_unknown_foreign_or_repeated_is_refused(world: CorrWorld) -> None:
    known = world.forge_item("P123-COR-0001", state="Received")
    foreign = world.forge_technical("P123-RFI-0050", scope="project:OTHER")
    before = count_events(world)
    with acting():
        for refs, error in (
            ([{"record_id": "01J000000000000000000000"}], RecordNotFoundError),
            ([{"record_id": foreign}], RecordNotFoundError),
            ([{"record_id": known}, {"record_id": known}], InvalidItemError),
        ):
            with pytest.raises(error):
                world.raise_commercial(references=refs)
    assert count_events(world) == before


def test_a_raise_outside_a_project_scope_is_refused(world: CorrWorld) -> None:
    with acting(), pytest.raises(CorrespondenceScopeError):
        world.raise_commercial(scope="company")


def test_a_plain_viewer_cannot_raise_a_commercial_item(world: CorrWorld) -> None:
    before = count_events(world)
    with frozen_today(MONDAY), pytest.raises(ForbiddenError):
        world.raise_commercial()
    assert count_events(world) == before


# --- UpdateCommercial -----------------------------------------------------------------------


def test_an_update_changes_the_given_fields_and_keeps_the_rest(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial(
            currency="USD", estimated_value="1000", entitlement_basis="Clause 20.1"
        )
        done = world.update_commercial(
            made.stream_id,
            subject="Early warning: re-routing",
            body="New text.",
            estimated_value="12500",
            estimated_hours="8",
            cost_code_impacts=[{"cost_code": "2.3.1", "amount": "12500"}],
            schedule_impact_days=5,
            to=[{"name": "Designer", "email": "d@design.example"}],
            reason="figures agreed",
        )
        row = world.commercial("P123-EW-0001")
    assert done.version > made.version and done.key == "P123-EW-0001"
    assert [e.event_type for e in done.events] == [
        "Record.Updated",
        "Correspondence.Updated",
        "Commercial.Updated",
    ]
    assert row.item.subject == "Early warning: re-routing" and row.item.body == "New text."
    assert [r["name"] for r in row.item.to] == ["Designer"]
    data = row.data
    assert (data.estimated_value, data.estimated_hours, data.schedule_impact_days) == (
        "12500.00",
        "8.0",
        5,
    )
    assert [i["cost_code"] for i in data.cost_code_impacts] == ["2.3.1"]
    assert (data.currency, data.entitlement_basis) == ("USD", "Clause 20.1")  # kept
    updated = payload(world, made.stream_id, "Commercial.Updated")
    assert updated["reason"] == "figures agreed"
    assert set(updated["changes"]) == {
        "estimated_value",
        "estimated_hours",
        "cost_code_impacts",
        "schedule_impact_days",
    }


def test_a_null_clears_an_optional_field_and_an_empty_list_clears_the_impacts(
    world: CorrWorld,
) -> None:
    with acting():
        made = world.raise_commercial(
            currency="USD",
            estimated_value="1000",
            schedule_impact_days=2,
            schedule_impact_note="note",
            entitlement_basis="basis",
            cost_code_impacts=[{"cost_code": "2.3.1", "amount": "1000"}],
        )
        world.update_commercial(
            made.stream_id,
            estimated_value=None,
            schedule_impact_days=None,
            schedule_impact_note=None,
            entitlement_basis=None,
            cost_code_impacts=[],
        )
        data = world.commercial("P123-EW-0001").data
    assert (data.estimated_value, data.schedule_impact_days, data.schedule_impact_note) == (
        None,
        None,
        None,
    )
    assert data.entitlement_basis is None and data.cost_code_impacts == []
    assert data.currency == "USD"


def test_an_amount_still_needs_a_currency_after_the_update(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial()
        before = count_events(world)
        with pytest.raises(InvalidItemError, match="currency"):
            world.update_commercial(made.stream_id, estimated_value="100")
        with pytest.raises(InvalidItemError, match="currency"):
            world.update_commercial(
                made.stream_id, cost_code_impacts=[{"cost_code": "2.3.1", "amount": "1"}]
            )
        world.update_commercial(made.stream_id, estimated_value="100", currency="EUR")
        with pytest.raises(InvalidItemError, match="currency"):
            world.update_commercial(made.stream_id, currency=None)
        with pytest.raises(InvalidItemError, match="once"):
            world.update_commercial(
                made.stream_id,
                cost_code_impacts=[
                    {"cost_code": "A", "amount": "1"},
                    {"cost_code": "A", "amount": "2"},
                ],
            )
        assert count_events(world) == before + 1


def test_the_clause_and_the_awareness_day_cannot_be_updated(world: CorrWorld) -> None:
    world.forge_clause("CT-1", "20.1")
    with acting():
        made = world.raise_commercial()
        for field, value in (("clause", "CT-1/20.1"), ("aware_on", MONDAY), ("subtype", "x")):
            with pytest.raises(ValidationError):
                world.update_commercial(made.stream_id, **{field: value})


def test_recipients_are_a_list_and_a_null_list_is_refused(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial()
        world.update_commercial(
            made.stream_id, to=[], cc=[{"name": "Site", "email": "s@x.example"}]
        )
        item = world.commercial("P123-EW-0001").item
        assert item.to == [] and [r["name"] for r in item.cc] == ["Site"]
        with pytest.raises(InvalidItemError, match="send \\[\\] to clear"):
            world.update_commercial(made.stream_id, cc=None)


def test_an_update_that_changes_nothing_is_refused(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial(currency="USD", estimated_value="100")
        with pytest.raises(NoChangesError):
            world.update_commercial(made.stream_id, estimated_value="100.00")
        with pytest.raises(NoChangesError):
            world.update_commercial(made.stream_id, subject="Early warning: routing change")
        with pytest.raises(NoChangesError):
            world.update_commercial(made.stream_id)


def test_an_item_in_commercial_review_may_be_changed_but_a_later_one_may_not(
    world: CorrWorld,
) -> None:
    with acting():
        made = world.raise_commercial()
        world.submit_commercial(made.stream_id)
        world.update_commercial(made.stream_id, schedule_impact_days=1, reason="review")
        world.review_commercial(made.stream_id)
        with pytest.raises(ItemStateError):
            world.update_commercial(made.stream_id, schedule_impact_days=2)


@pytest.mark.parametrize(
    "state", ["PM approval", "Awaiting assessment", "Agreed", "Disputed", "Closed", "Escalated"]
)
def test_no_state_after_review_takes_a_change(world: CorrWorld, state: str) -> None:
    item_id = world.forge_commercial("P123-EW-0009", state=state)
    with acting(), pytest.raises(ItemStateError):
        world.update_commercial(item_id, schedule_impact_days=1)


def test_an_update_on_a_stale_version_is_a_conflict(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial()
        world.update_commercial(made.stream_id, schedule_impact_days=1)
        with pytest.raises(ConcurrencyError):
            world.update_commercial(
                made.stream_id, schedule_impact_days=2, expected_version=made.version
            )


def test_an_update_of_something_that_is_not_a_readable_commercial_item_is_not_found(
    world: CorrWorld,
) -> None:
    rfi = world.forge_technical("P123-RFI-0001")
    foreign = world.forge_commercial("P123-EW-0005", scope="project:OTHER")
    secret = world.forge_commercial("P123-EW-0006", confidentiality="privileged")
    with acting():
        for target in (rfi, foreign, secret, "01J000000000000000000000"):
            with pytest.raises(RecordNotFoundError):
                world.update_commercial(target, schedule_impact_days=1)


# --- SubmitCommercial, ReviewCommercial, ReturnCommercial -----------------------------------


def test_a_draft_goes_to_review_then_to_pm_approval_with_a_note(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial()
        submitted = world.submit_commercial(made.stream_id)
        assert world.commercial("P123-EW-0001").item.state == "Commercial review"
        reviewed = world.review_commercial(made.stream_id, note="figures checked")
        assert world.commercial("P123-EW-0001").item.state == "PM approval"
    assert made.version < submitted.version < reviewed.version
    moves = [p for n, p in world.events_of(made.stream_id) if n == "Workflow.Transitioned"]
    assert [m["reason"] for m in moves] == [None, "figures checked"]


def test_a_notice_to_the_client_needs_a_recipient(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial(to=[])
        with pytest.raises(InvalidItemError, match="needs a recipient before review"):
            world.submit_commercial(made.stream_id)
        world.update_commercial(made.stream_id, to=[{"name": "A", "email": "a@x.example"}])
        world.submit_commercial(made.stream_id)


@pytest.mark.parametrize(
    ("subtype", "fields", "missing"),
    [
        ("change_notice", {}, "entitlement_basis"),
        ("claim_notice", {}, "entitlement_basis, contract_clause_id"),
        ("claim_notice", {"entitlement_basis": "Clause 20.1"}, "contract_clause_id"),
        (
            "detailed_claim",
            {"entitlement_basis": "b", "clause": "CT-1/20.1"},
            "estimated_value, cost_code_impacts",
        ),
        (
            "detailed_claim",
            {
                "entitlement_basis": "b",
                "clause": "CT-1/20.1",
                "currency": "USD",
                "estimated_value": "5",
            },
            "cost_code_impacts",
        ),
    ],
)
def test_a_subtype_needs_its_data_before_review(
    world: CorrWorld, subtype: str, fields: dict[str, Any], missing: str
) -> None:
    world.forge_clause("CT-1", "20.1")
    with acting():
        made = world.raise_commercial(subtype=subtype, **fields)
        with pytest.raises(InvalidItemError) as raised:
            world.submit_commercial(made.stream_id)
        assert f"needs {missing} before review" in str(raised.value)
        assert world.commercial(made.key or "").item.state == "Draft"


def test_a_claim_with_its_basis_and_clause_goes_to_review(world: CorrWorld) -> None:
    world.forge_clause("CT-1", "20.1")
    with acting():
        made = world.raise_commercial(
            subtype="detailed_claim",
            clause="CT-1/20.1",
            entitlement_basis="Clause 20.1",
            currency="USD",
            estimated_value="9000",
            cost_code_impacts=[{"cost_code": "2.3.1", "amount": "9000"}],
        )
        world.submit_commercial(made.stream_id)
        assert world.commercial(made.key or "").item.state == "Commercial review"


def test_only_a_draft_is_submitted_and_only_an_item_in_review_is_reviewed(
    world: CorrWorld,
) -> None:
    with acting():
        made = world.raise_commercial()
        with pytest.raises(ItemStateError):
            world.review_commercial(made.stream_id)
        world.submit_commercial(made.stream_id)
        with pytest.raises(ItemStateError):
            world.submit_commercial(made.stream_id)
        world.review_commercial(made.stream_id)
        with pytest.raises(ItemStateError):
            world.review_commercial(made.stream_id)
        with pytest.raises(ItemStateError):
            world.submit_commercial(made.stream_id)


def test_an_item_is_returned_from_review_or_from_pm_approval_with_a_reason(
    world: CorrWorld,
) -> None:
    with acting():
        made = world.raise_commercial()
        with pytest.raises(ItemStateError):  # a Draft is not returned
            world.return_commercial(made.stream_id)
        world.submit_commercial(made.stream_id)
        world.return_commercial(made.stream_id, reason="figures missing")
        assert world.commercial("P123-EW-0001").item.state == "Draft"
        world.submit_commercial(made.stream_id)
        world.review_commercial(made.stream_id)
        world.return_commercial(made.stream_id, reason="PM wants a lower figure")
        assert world.commercial("P123-EW-0001").item.state == "Draft"
        for blank in ("", "   "):
            world.submit_commercial(made.stream_id)
            with pytest.raises(ValidationError):
                world.return_commercial(made.stream_id, reason=blank)
            world.return_commercial(made.stream_id, reason="again")
    reasons = [
        p["reason"] for n, p in world.events_of(made.stream_id) if n == "Workflow.Transitioned"
    ]
    assert "figures missing" in reasons and "PM wants a lower figure" in reasons


def test_a_later_state_is_not_returned(world: CorrWorld) -> None:
    waiting = world.forge_commercial("P123-EW-0007", state="Awaiting assessment")
    with acting(), pytest.raises(ItemStateError):
        world.return_commercial(waiting)


def test_every_command_refuses_a_plain_viewer_and_a_hidden_or_unknown_item(
    world: CorrWorld,
) -> None:
    with acting():
        made = world.raise_commercial()
    commands: list[Any] = [
        lambda i: world.update_commercial(i, schedule_impact_days=1),
        world.submit_commercial,
        world.review_commercial,
        world.return_commercial,
    ]
    before = count_events(world)
    with frozen_today(MONDAY):
        for command in commands:
            with pytest.raises(ForbiddenError):
                command(made.stream_id)
    with acting():
        for command in commands:
            with pytest.raises(RecordNotFoundError):
                command("01J000000000000000000000")
    assert count_events(world) == before


def test_a_recipient_that_names_a_party_needs_a_party_of_the_project(world: CorrWorld) -> None:
    party = world.forge_party("MER", "Meridian Energy")
    with acting():
        made = world.raise_commercial(to=[{"name": "Meridian", "party_id": party}])
        world.update_commercial(made.stream_id, cc=[{"party_id": party}])
        before = count_events(world)
        for field in ("to", "cc"):
            with pytest.raises(InvalidItemError, match="is not a party of"):
                world.update_commercial(made.stream_id, **{field: [{"party_id": "NOSUCH"}]})
        with pytest.raises(InvalidItemError, match="is not a party of"):
            world.raise_commercial(to=[{"party_id": "NOSUCH"}])
    assert count_events(world) == before


def test_a_plain_viewer_is_refused_before_anything_else_is_looked_at(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        for fields in ({"subtype": "nonsense"}, {"scope": "company"}, {"clause": "NOPE/1"}):
            with pytest.raises(ForbiddenError):
                world.raise_commercial(**fields)


def test_a_transition_on_a_stale_version_is_a_conflict(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial()
        world.update_commercial(made.stream_id, schedule_impact_days=1)  # the item moved on
        with pytest.raises(ConcurrencyError):
            world.submit_commercial(made.stream_id, expected_version=made.version)
        world.submit_commercial(made.stream_id)
        stale = world.commercial("P123-EW-0001").item.version - 1
        with pytest.raises(ConcurrencyError):
            world.review_commercial(made.stream_id, expected_version=stale)
        with pytest.raises(ConcurrencyError):
            world.return_commercial(made.stream_id, expected_version=stale)
        current = world.commercial("P123-EW-0001").item.version
        world.review_commercial(made.stream_id, expected_version=current)


def test_an_item_made_from_another_carries_the_link_the_class_and_the_readers(
    world: CorrWorld,
) -> None:
    """The escalation of an RFI makes the item with `create_commercial` (Python only)."""
    rfi = world.forge_technical("P123-RFI-0001", state="Answered")
    with acting(), open_uow(world.db) as uow:
        source = registry.get_item(uow.conn(), rfi)
        assert source is not None
        definition = catalog.check_subtype("project:P123", "commercial", "early_warning")
        raised = RaiseCommercial(
            **BASE, subtype="early_warning", subject="From the RFI", aware_on="2026-10-18"
        )
        made = create_commercial(
            uow,
            raised,
            definition=definition,
            derived_from=source,
            confidentiality_class="privileged",
            clearances=["user:amy", "user:ctl"],
        )
    with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
        row = world.commercial(made.key or "")
        assert row.data.derived_from_id == rfi and row.data.aware_on == "2026-10-18"
        assert row.item.confidentiality == "privileged"
        with open_uow(world.db, readonly=True) as uow:
            assert sorted(
                c.account for c in registry.clearances_of(uow.conn(), made.stream_id)
            ) == [
                "user:amy",
                "user:ctl",
            ]
    [link] = world.rows(
        "SELECT to_id, relation, source, note FROM cur_links WHERE from_id = :f", f=made.stream_id
    )
    assert (link["to_id"], link["relation"], link["source"]) == (rfi, "derived_from", "rule")
    assert link["note"] == "escalated from P123-RFI-0001"


def test_create_commercial_refuses_a_plain_viewer_itself(world: CorrWorld) -> None:
    definition = catalog.check_subtype("project:P123", "commercial", "early_warning")
    with frozen_today(MONDAY), open_uow(world.db) as uow, pytest.raises(ForbiddenError):
        create_commercial(
            uow,
            RaiseCommercial(**BASE, subtype="early_warning", subject="x"),
            definition=definition,
        )
