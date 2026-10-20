"""Issue, assess, close and refer a Commercial item (P1-I6-T04b).

The item is raised, reviewed and approved with the author's commands (`test_commercial.py`) and the
story is told from there: the notice goes out and meets its time bar (late or not); the other
party assesses it; the item is closed, or a dispute goes to the legal route. Every command is a
document controller's: the tests run as one (`acting`) and one test shows the refusals for a plain
viewer.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence.errors import (
    InvalidItemError,
    ItemBackdatedError,
    ItemStateError,
    LetterRenderError,
)
from tl_mod_correspondence.testing import CorrWorld, as_controller, frozen_today

MONDAY = "2026-10-19"


@contextmanager
def acting(day: str = MONDAY) -> Generator[None]:
    with frozen_today(day), as_controller():
        yield


def payloads(world: CorrWorld, stream_id: str, name: str) -> list[dict[str, Any]]:
    return [p for n, p in world.events_of(stream_id) if n == name]


def count_events(world: CorrWorld) -> int:
    return world.scalar("SELECT count(*) FROM events")


def approved(world: CorrWorld, subtype: str = "early_warning", **more: Any) -> str:
    """A notice raised on Monday and approved by the project manager (ready to issue)."""
    with acting():
        made = world.raise_commercial(subtype=subtype, **more)
        world.submit_commercial(made.stream_id)
        world.review_commercial(made.stream_id)
    return made.stream_id


def waiting(world: CorrWorld, subtype: str = "early_warning", **more: Any) -> str:
    """A notice issued on Monday and awaiting the other party's assessment."""
    item_id = approved(world, subtype, **more)
    with acting():
        world.issue_commercial(item_id)
    return item_id


def read(world: CorrWorld, number: str = "P123-EW-0001") -> Any:
    with as_controller():
        return world.commercial(number)


# --- IssueCommercial ------------------------------------------------------------------------


def test_issuing_sends_the_notice_meets_the_time_bar_and_waits_for_the_assessment(
    world: CorrWorld,
) -> None:
    item_id = approved(world)
    with acting("2026-10-21"):
        done = world.issue_commercial(item_id)
        bar, wait = world.clocks("P123-EW-0001")
        row = world.commercial("P123-EW-0001")
    assert row.item.state == "Awaiting assessment"
    assert (row.item.issued_on, row.item.delivery) == ("2026-10-21", "stub")
    assert done.key == "P123-EW-0001" and done.version == row.item.version
    assert (bar.kind, bar.state, bar.closed_on, bar.closed_reason) == (
        "time_bar",
        "met",
        "2026-10-21",
        "the notice was issued",
    )
    assert bar.due_on == "2026-11-02"  # met in time: closed before the due day
    assert (wait.kind, wait.state, wait.start_on, wait.label) == (
        "response_from_them",
        "running",
        "2026-10-21",
        "Assessment expected",
    )
    assert (wait.day_type, wait.duration_days) == ("working", 14)
    [issued] = payloads(world, item_id, "Correspondence.Issued")
    assert (issued["issued_on"], issued["date_reason"], issued["delivery"]) == (
        "2026-10-21",
        None,
        "stub",
    )
    assert issued["template"] == "commercial-early-warning"
    assert issued["clock_ids"] == [wait.id]
    assert issued["feed_policy"] == "minimal"
    assert issued["feed_text"] == "A commercial notice was issued"
    moves = [p["transition"] for p in payloads(world, item_id, "Workflow.Transitioned")]
    assert moves[-2:] == ["issue", "await_assessment"]


def test_a_notice_issued_after_its_time_bar_is_issued_all_the_same_and_the_bar_shows_late(
    world: CorrWorld,
) -> None:
    item_id = approved(world, aware_on="2026-10-01")  # 14 calendar days: due 2026-10-15
    with acting("2026-10-19"):
        world.issue_commercial(item_id)
        bar, _ = world.clocks("P123-EW-0001")
    assert read(world).item.state == "Awaiting assessment"
    assert (bar.due_on, bar.state, bar.closed_on) == ("2026-10-15", "met", "2026-10-19")
    assert bar.closed_on is not None and bar.closed_on > bar.due_on


def test_the_notice_is_a_pdf_with_the_figures_the_basis_and_the_clause(world: CorrWorld) -> None:
    world.forge_clause("CT-1", "20.1")
    item_id = approved(
        world,
        subtype="change_notice",
        clause="CT-1/20.1",
        currency="USD",
        estimated_value="12500",
        estimated_hours="240",
        schedule_impact_days=3,
        schedule_impact_note="Spool S-14 is critical.",
        entitlement_basis="Clause 20.1 applies",
    )
    with acting():
        world.issue_commercial(item_id)
    [issued] = payloads(world, item_id, "Correspondence.Issued")
    assert world.files is not None
    with open_uow(world.db, readonly=True) as uow, as_controller():
        opened = world.files.open_file(
            uow, "project:P123", issued["rendition_file_id"], actor="user:u"
        )
        try:
            data = opened.data.read()
        finally:
            opened.data.close()
    assert data.startswith(b"%PDF-")
    for text in (
        b"P123-CN-0001",
        b"Early warning: routing change",
        b"re-routing changes the scope",
        b"Estimated value: USD 12500.00",
        b"Estimated hours: 240.0",
        b"Schedule impact: 3 days",
        b"Spool S-14 is critical.",
        b"Basis: Clause 20.1 applies",
        b"Given under clause CT-1/20.1.",
        b"Meridian Energy",
    ):
        assert text in data, text
    assert issued["template"] == "commercial-change-notice"


def test_issuing_meets_the_time_bar_only_and_leaves_a_clock_a_person_started(
    world: CorrWorld,
) -> None:
    item_id = approved(world)
    with acting():
        world.start_clock(item_id, label="Reply expected from them")  # response_from_them
        world.issue_commercial(item_id)
        bar, started, _ = world.clocks("P123-EW-0001")
    assert (bar.kind, bar.state) == ("time_bar", "met")
    assert (started.label, started.kind, started.state) == (
        "Reply expected from them",
        "response_from_them",
        "running",
    )


def test_a_quotation_has_no_bar_to_meet_and_starts_its_own_clock(world: CorrWorld) -> None:
    item_id = approved(world, subtype="quotation")
    with acting():
        world.issue_commercial(item_id)
        [accept] = world.clocks("P123-QT-0001")
    assert (accept.label, accept.state, accept.duration_days) == (
        "Acceptance expected",
        "running",
        28,
    )
    [issued] = payloads(world, item_id, "Correspondence.Issued")
    assert issued["clock_ids"] == [accept.id]


def test_an_earlier_issue_day_needs_a_reason_and_a_later_one_is_never_allowed(
    world: CorrWorld,
) -> None:
    item_id = approved(world)
    with acting("2026-10-21"):
        for bad in ({"issued_on": "2026-10-20"}, {"issued_on": "2026-10-20", "date_reason": " "}):
            with pytest.raises(ItemBackdatedError):
                world.issue_commercial(item_id, **bad)
        with pytest.raises(ItemBackdatedError):
            world.issue_commercial(item_id, issued_on="2026-10-22", date_reason="soon")
        world.issue_commercial(item_id, issued_on="2026-10-20", date_reason="posted on Tuesday")
        bar, wait = world.clocks("P123-EW-0001")
    [issued] = payloads(world, item_id, "Correspondence.Issued")
    assert (issued["issued_on"], issued["date_reason"]) == ("2026-10-20", "posted on Tuesday")
    assert bar.closed_on == "2026-10-20" and wait.start_on == "2026-10-20"


def test_a_notice_is_not_issued_on_a_day_before_the_contractor_became_aware(
    world: CorrWorld,
) -> None:
    item_id = approved(world, aware_on="2026-10-15")
    with acting():
        before = count_events(world)
        with pytest.raises(InvalidItemError, match="before the day the contractor became aware"):
            world.issue_commercial(item_id, issued_on="2026-10-14", date_reason="posted early")
        assert count_events(world) == before
        world.issue_commercial(item_id, issued_on="2026-10-15", date_reason="posted that day")
    assert read(world).item.issued_on == "2026-10-15"


def test_a_named_template_is_used_and_an_unknown_one_is_refused(world: CorrWorld) -> None:
    item_id = approved(world)
    with acting():
        before = count_events(world)
        with pytest.raises(LetterRenderError, match="no letter template 'nonsense'"):
            world.issue_commercial(item_id, template="nonsense")
        assert count_events(world) == before
        world.issue_commercial(item_id, template="commercial-quotation")
    assert payloads(world, item_id, "Correspondence.Issued")[0]["template"] == (
        "commercial-quotation"
    )


def test_only_an_item_in_pm_approval_with_a_recipient_is_issued(world: CorrWorld) -> None:
    with acting():
        draft = world.raise_commercial()
        with pytest.raises(ItemStateError):
            world.issue_commercial(draft.stream_id)
        world.submit_commercial(draft.stream_id)
        with pytest.raises(ItemStateError):  # commercial review, not yet approved
            world.issue_commercial(draft.stream_id)
    nobody = world.forge_commercial("P123-EW-0004", state="PM approval", item={"to": []})
    with acting(), pytest.raises(InvalidItemError, match="has no recipient"):
        world.issue_commercial(nobody)
    done = waiting(world, subject="Second warning")
    with acting(), pytest.raises(ItemStateError):
        world.issue_commercial(done)


# --- AssessCommercial -----------------------------------------------------------------------


def test_an_agreed_assessment_records_the_value_and_meets_the_clock(world: CorrWorld) -> None:
    item_id = waiting(world, currency="USD", estimated_value="12500")
    with acting("2026-11-02"):
        done = world.assess_commercial(item_id, "agreed", assessed_value="11000", note="as stated")
        row = world.commercial("P123-EW-0001")
        [_, wait] = world.clocks("P123-EW-0001")
    assert row.item.state == "Agreed" and done.version == row.item.version
    data = row.data
    assert (data.assessment_status, data.assessed_value, data.assessed_on) == (
        "agreed",
        "11000.00",
        "2026-11-02",
    )
    assert data.assessment_note == "as stated"
    assert (wait.state, wait.closed_on, wait.closed_reason) == ("met", "2026-11-02", "assessed")
    [assessed] = payloads(world, item_id, "Commercial.Assessed")
    assert assessed["feed_policy"] == "minimal"
    assert assessed["feed_text"] == "A commercial notice was assessed"
    assert assessed["date_reason"] is None
    [moved] = payloads(world, item_id, "Workflow.Transitioned")[-1:]
    assert (moved["transition"], moved["reason"]) == ("agree", "as stated")


@pytest.mark.parametrize(
    ("status", "state", "move"),
    [
        ("agreed", "Agreed", "agree"),
        ("partially_agreed", "Partially agreed", "part_agree"),
        ("disputed", "Disputed", "dispute"),
    ],
)
def test_each_assessment_moves_the_item_to_its_own_state(
    world: CorrWorld, status: str, state: str, move: str
) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    value = None if status == "disputed" else "80"
    with acting():
        world.assess_commercial(item_id, status, assessed_value=value)
    assert read(world).item.state == state
    assert payloads(world, item_id, "Workflow.Transitioned")[-1]["transition"] == move


def test_a_dispute_may_state_no_value_and_an_agreement_may_not(world: CorrWorld) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting():
        before = count_events(world)
        with pytest.raises(InvalidItemError, match="agreed item needs the assessed value"):
            world.assess_commercial(item_id, "agreed", assessed_value=None)
        with pytest.raises(
            InvalidItemError, match="partially agreed item needs the assessed value"
        ):
            world.assess_commercial(item_id, "partially_agreed", assessed_value=None)
        assert count_events(world) == before
        world.assess_commercial(item_id, "disputed")
    data = read(world).data
    assert (data.assessment_status, data.assessed_value) == ("disputed", None)


def test_a_value_needs_a_currency_on_the_item(world: CorrWorld) -> None:
    item_id = waiting(world)  # no figures stated, so no currency
    with acting():
        with pytest.raises(InvalidItemError, match="states no currency"):
            world.assess_commercial(item_id, "agreed", assessed_value="100")
        world.assess_commercial(item_id, "disputed")


def test_an_earlier_assessment_day_needs_a_reason_and_the_clock_ends_on_that_day(
    world: CorrWorld,
) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting("2026-11-04"):
        with pytest.raises(ItemBackdatedError):
            world.assess_commercial(
                item_id, "agreed", assessed_value="90", assessed_on="2026-11-02"
            )
        with pytest.raises(ItemBackdatedError):
            world.assess_commercial(
                item_id, "agreed", assessed_value="90", assessed_on="2026-11-05"
            )
        world.assess_commercial(
            item_id,
            "agreed",
            assessed_value="90",
            assessed_on="2026-11-02",
            date_reason="the letter is dated Monday",
        )
        [_, wait] = world.clocks("P123-EW-0001")
    [assessed] = payloads(world, item_id, "Commercial.Assessed")
    assert (assessed["assessed_on"], assessed["date_reason"]) == (
        "2026-11-02",
        "the letter is dated Monday",
    )
    assert wait.closed_on == "2026-11-02"


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "maybe"},
        {"status": "agreed", "assessed_value": "12.345"},
        {"status": "agreed", "assessed_value": "-5"},
        {"status": "agreed", "assessed_value": "1,000"},
    ],
)
def test_an_assessment_that_cannot_be_used_is_refused(
    world: CorrWorld, fields: dict[str, Any]
) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting(), pytest.raises(ValidationError):
        world.assess_commercial(item_id, **fields)


def test_only_an_item_awaiting_assessment_is_assessed(world: CorrWorld) -> None:
    draft = world.forge_commercial("P123-EW-0010")
    agreed = world.forge_commercial("P123-EW-0011", state="Agreed")
    with acting():
        for target in (draft, agreed):
            with pytest.raises(ItemStateError):
                world.assess_commercial(target, "disputed")


def test_a_site_instruction_we_received_is_assessed_from_the_start(world: CorrWorld) -> None:
    with acting():
        made = world.raise_commercial("SI 7", subtype="site_instruction", to=[])
        world.assess_commercial(made.stream_id, "disputed", note="we will claim")
        row = world.commercial("P123-SI-0001")
    assert row.item.state == "Disputed" and row.data.assessment_note == "we will claim"


# --- CloseCommercial ------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["agreed", "partially_agreed"])
def test_an_agreed_item_closes_without_a_reason(world: CorrWorld, status: str) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting("2026-11-03"):
        world.assess_commercial(item_id, status, assessed_value="90")
        done = world.close_commercial(item_id)
        row = world.commercial("P123-EW-0001")
    assert row.item.state == "Closed" and row.item.closed is True
    assert done.version == row.item.version


def test_a_disputed_item_closes_only_with_a_reason(world: CorrWorld) -> None:
    item_id = waiting(world)
    with acting():
        world.assess_commercial(item_id, "disputed")
        for blank in (None, "", "  "):
            with pytest.raises(ItemStateError, match="give the reason for closing"):
                world.close_commercial(item_id, reason=blank)
        world.close_commercial(item_id, reason="settled in the next valuation")
    assert read(world).item.state == "Closed"
    [moved] = payloads(world, item_id, "Workflow.Transitioned")[-1:]
    assert (moved["transition"], moved["reason"]) == ("close", "settled in the next valuation")


def test_closing_cancels_the_clocks_that_are_still_open(world: CorrWorld) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting("2026-11-03"):
        world.assess_commercial(item_id, "agreed", assessed_value="90")
        world.start_clock(item_id, label="Payment expected")
        world.close_commercial(item_id)
        bar, wait, extra = world.clocks("P123-EW-0001")
    assert (bar.state, wait.state) == ("met", "met")
    assert (extra.state, extra.closed_on, extra.closed_reason) == (
        "cancelled",
        "2026-11-03",
        "item closed",
    )


@pytest.mark.parametrize(
    "state", ["Draft", "Commercial review", "PM approval", "Awaiting assessment"]
)
def test_no_other_state_is_closed(world: CorrWorld, state: str) -> None:
    item_id = world.forge_commercial("P123-EW-0020", state=state)
    with acting(), pytest.raises(ItemStateError):
        world.close_commercial(item_id, reason="x")


def test_a_closed_item_takes_no_more(world: CorrWorld) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting():
        world.assess_commercial(item_id, "agreed", assessed_value="90")
        world.close_commercial(item_id)
        for command in (
            lambda: world.close_commercial(item_id),
            lambda: world.assess_commercial(item_id, "agreed"),
            lambda: world.update_commercial(item_id, schedule_impact_days=1),
        ):
            with pytest.raises(ItemStateError, match="takes no more changes"):
                command()


# --- ReferCommercialToLegal -----------------------------------------------------------------


def test_a_disputed_item_goes_to_the_legal_route_and_its_clocks_are_cancelled(
    world: CorrWorld,
) -> None:
    item_id = waiting(world)
    with acting("2026-11-03"):
        world.assess_commercial(item_id, "disputed")
        world.start_clock(item_id, label="Reply to the dispute")
        done = world.refer_to_legal(item_id, reason="the claim is formal")
        row = world.commercial("P123-EW-0001")
        *_, extra = world.clocks("P123-EW-0001")
    assert row.item.state == "Escalated" and done.version == row.item.version
    assert (extra.state, extra.closed_reason) == ("cancelled", "referred to the legal route")
    [moved] = payloads(world, item_id, "Workflow.Transitioned")[-1:]
    assert (moved["transition"], moved["reason"]) == ("escalate", "the claim is formal")


def test_only_a_disputed_item_is_referred_and_a_reason_is_required(world: CorrWorld) -> None:
    item_id = waiting(world, currency="USD", estimated_value="100")
    with acting():
        with pytest.raises(ItemStateError):
            world.refer_to_legal(item_id)
        world.assess_commercial(item_id, "agreed", assessed_value="90")
        with pytest.raises(ItemStateError):
            world.refer_to_legal(item_id)
    other = world.forge_commercial("P123-EW-0030", state="Disputed")
    with acting():
        for blank in ("", "   "):
            with pytest.raises(ValidationError):
                world.refer_to_legal(other, reason=blank)
        world.refer_to_legal(other)
        with pytest.raises(ItemStateError):
            world.refer_to_legal(other)


# --- who may --------------------------------------------------------------------------------


def test_every_command_refuses_a_plain_viewer_and_a_hidden_or_unknown_item(
    world: CorrWorld,
) -> None:
    ready = approved(world)
    commands: list[Any] = [
        world.issue_commercial,
        lambda i: world.assess_commercial(i, "disputed"),
        world.close_commercial,
        world.refer_to_legal,
    ]
    secret = world.forge_commercial(
        "P123-EW-0040", state="PM approval", confidentiality="privileged"
    )
    before = count_events(world)
    with frozen_today(MONDAY):
        for command in commands:
            with pytest.raises(ForbiddenError):
                command(ready)
    with acting():
        for command in commands:
            for target in (secret, "01J000000000000000000000"):
                with pytest.raises(RecordNotFoundError):
                    command(target)
    assert count_events(world) == before
