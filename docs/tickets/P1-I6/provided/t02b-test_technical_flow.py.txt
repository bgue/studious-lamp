"""Issue, answer, judge, re-issue and close a Technical item (P1-I6-T02b).

The item is raised and sent through the raiser's commands (`test_technical.py`) and the story is
told from there: a letter goes out and a clock counts to the date the answer is needed; the answer
meets the clock; the raiser accepts it or sends the question round again; a closed item takes no
more.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence import constraints
from tl_mod_correspondence.errors import (
    InvalidClockError,
    InvalidItemError,
    ItemBackdatedError,
    ItemStateError,
    LetterRenderError,
)
from tl_mod_correspondence.handlers.technical_flow import AnswerTechnical, handle_answer_technical
from tl_mod_correspondence.testing import CONTROLLER, CorrWorld, frozen_today
from tl_mod_documents.testing import DocumentsWorld

MONDAY = "2026-10-19"
DUE = "2026-11-02"


def names(world: CorrWorld, stream_id: str) -> list[str]:
    return [n for n, _ in world.events_of(stream_id)]


def payloads(world: CorrWorld, stream_id: str, name: str) -> list[dict[str, Any]]:
    return [p for n, p in world.events_of(stream_id) if n == name]


def review(world: CorrWorld, **more: Any) -> str:
    """An RFI in internal review, raised on Monday and needed by ``DUE``."""
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=DUE, **more)
        world.submit_technical(made.stream_id)
    return made.stream_id


def awaiting(world: CorrWorld, **more: Any) -> str:
    """An RFI issued on Monday and awaiting its answer."""
    item_id = review(world, **more)
    with frozen_today(MONDAY), cf.use_viewer(CONTROLLER):
        world.issue_technical(item_id)
    return item_id


def count_events(world: CorrWorld) -> int:
    return world.scalar("SELECT count(*) FROM events")


# --- IssueTechnical -------------------------------------------------------------------------


def test_issuing_sends_the_letter_counts_to_the_date_needed_and_waits_for_the_answer(
    world: CorrWorld,
) -> None:
    item_id = review(world, proposed_solution="Move the beam 200 mm east.")
    with frozen_today(MONDAY):
        done = world.issue_technical(item_id)
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Awaiting response"
    assert (row.item.issued_on, row.item.delivery) == (MONDAY, "stub")
    assert done.key == "P123-RFI-0001" and done.version == row.item.version
    issued = payloads(world, item_id, "Correspondence.Issued")
    [first] = issued
    assert (first["issued_on"], first["date_reason"], first["delivery"]) == (MONDAY, None, "stub")
    assert first["template"] == "technical-rfi"
    assert first["feed_policy"] == "full"
    assert first["feed_text"] == "P123-RFI-0001 issued: Beam B12 clashes with line 47"
    [moved_in, moved_out] = [
        p["transition"] for p in payloads(world, item_id, "Workflow.Transitioned")[-2:]
    ]
    assert (moved_in, moved_out) == ("issue", "await_response")
    [clock] = world.clocks("P123-RFI-0001")
    assert (clock.kind, clock.state, clock.start_on, clock.due_on) == (
        "response_from_them",
        "running",
        MONDAY,
        DUE,
    )
    assert (clock.day_type, clock.duration_days, clock.label) == ("calendar", 14, "Answer required")
    assert clock.warn_days == [3, 1]
    assert first["clock_ids"] == [clock.id]


def test_the_letter_is_a_pdf_with_the_number_the_question_and_the_date_needed(
    world: CorrWorld,
) -> None:
    item_id = awaiting(world, proposed_solution="Move the beam 200 mm east.")
    [issued] = payloads(world, item_id, "Correspondence.Issued")
    assert world.files is not None
    with open_uow(world.db, readonly=True) as uow:
        opened = world.files.open_file(
            uow, "project:P123", issued["rendition_file_id"], actor="user:u"
        )
        try:
            data = opened.data.read()
        finally:
            opened.data.close()
    assert data.startswith(b"%PDF-")
    for text in (
        b"P123-RFI-0001",
        b"Beam B12 clashes with line 47",
        b"confirm the routing",
        b"Proposed solution",
        b"Move the beam 200 mm east.",
        b"An answer is needed by 2026-11-02.",
        b"Meridian Energy",
    ):
        assert text in data, text


def test_each_subtype_uses_its_own_template(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(subtype="deviation", required_by=DUE)
        world.submit_technical(made.stream_id)
        world.issue_technical(made.stream_id)
    [issued] = payloads(world, made.stream_id, "Correspondence.Issued")
    assert issued["template"] == "technical-deviation"
    [clock] = world.clocks("P123-DEV-0001")
    assert clock.label == "Disposition required"


def test_a_named_template_is_used_and_an_unknown_one_is_refused(world: CorrWorld) -> None:
    item_id = review(world)
    with frozen_today(MONDAY):
        before = count_events(world)
        with pytest.raises(LetterRenderError, match="no letter template 'nonsense'"):
            world.issue_technical(item_id, template="nonsense")
        assert count_events(world) == before
        world.issue_technical(item_id, template="technical-tq")
    assert payloads(world, item_id, "Correspondence.Issued")[0]["template"] == "technical-tq"


def test_an_earlier_issue_day_needs_a_reason_and_a_later_one_is_never_allowed(
    world: CorrWorld,
) -> None:
    item_id = review(world)
    with frozen_today("2026-10-21"):
        for bad in ({"issued_on": "2026-10-20"}, {"issued_on": "2026-10-20", "date_reason": " "}):
            with pytest.raises(ItemBackdatedError):
                world.issue_technical(item_id, **bad)
        with pytest.raises(ItemBackdatedError):
            world.issue_technical(item_id, issued_on="2026-10-22", date_reason="soon")
        world.issue_technical(item_id, issued_on="2026-10-20", date_reason="posted on Tuesday")
    [issued] = payloads(world, item_id, "Correspondence.Issued")
    assert (issued["issued_on"], issued["date_reason"]) == ("2026-10-20", "posted on Tuesday")
    [clock] = world.clocks("P123-RFI-0001")
    assert clock.start_on == "2026-10-20"
    assert world.technical("P123-RFI-0001").item.issued_on == "2026-10-20"


def test_the_answer_must_be_needed_after_the_day_of_issue(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by=MONDAY)
        world.submit_technical(made.stream_id)
        before = count_events(world)
        with pytest.raises(InvalidClockError, match="not after"):
            world.issue_technical(made.stream_id)
    assert count_events(world) == before
    assert world.technical("P123-RFI-0001").item.state == "Internal review"


def test_only_an_item_in_internal_review_with_a_recipient_is_issued(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.raise_technical(required_by=DUE)
        with pytest.raises(ItemStateError):
            world.issue_technical(draft.stream_id)
    nobody = world.forge_technical(
        "P123-RFI-0004", state="Internal review", item={"to": []}, required_by=DUE
    )
    with frozen_today(MONDAY), pytest.raises(InvalidItemError, match="has no recipient"):
        world.issue_technical(nobody)
    waiting = awaiting(world)
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.issue_technical(waiting)


def test_issuing_something_that_is_not_a_readable_technical_item_is_not_found(
    world: CorrWorld,
) -> None:
    letter = world.forge_item("P123-COR-0001", state="Received")
    secret = world.forge_technical(
        "P123-RFI-0006", state="Internal review", confidentiality="restricted"
    )
    foreign = world.forge_technical("P123-RFI-0007", state="Internal review", scope="project:OTHER")
    with frozen_today(MONDAY):
        for target in (letter, secret, foreign, "01J000000000000000000000"):
            with pytest.raises(RecordNotFoundError):
                world.issue_technical(target)


# --- AnswerTechnical ------------------------------------------------------------------------


def test_an_answer_is_recorded_with_the_statement_on_cost_and_schedule(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today("2026-10-22"):
        done = world.answer_technical(
            item_id,
            answer="Keep the beam; shift the line.",
            cost_impact="yes",
            schedule_impact="no",
        )
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Answered"
    assert row.item.responded_on == "2026-10-22"
    data = row.data
    assert (data.answer, data.answered_on) == ("Keep the beam; shift the line.", "2026-10-22")
    assert (data.answer_cost_impact, data.answer_schedule_impact) == ("yes", "no")
    assert (data.answer_item_id, data.answering_revision_id) == (None, None)
    assert done.version == row.item.version and done.key == "P123-RFI-0001"
    [answered] = payloads(world, item_id, "Technical.Answered")
    assert answered["date_reason"] is None and answered["feed_policy"] == "full"
    assert answered["feed_text"] == "P123-RFI-0001 answered: Beam B12 clashes with line 47"
    [responded] = payloads(world, item_id, "Correspondence.Responded")
    assert responded == {"response_id": None, "responded_on": "2026-10-22"}


def test_the_flags_default_to_unknown(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY):
        world.run(AnswerTechnical, handle_answer_technical, stream_id=item_id, answer="Fine.")
    data = world.technical("P123-RFI-0001").data
    assert (data.answer_cost_impact, data.answer_schedule_impact) == ("unknown", "unknown")


def test_the_answer_meets_the_clock_on_the_day_it_came(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today("2026-10-22"):
        world.answer_technical(item_id, answer="Fine.")
    [clock] = world.clocks("P123-RFI-0001")
    assert (clock.state, clock.closed_on, clock.closed_reason) == ("met", "2026-10-22", "answered")


def test_an_earlier_answer_day_needs_a_reason_and_the_clock_ends_on_that_day(
    world: CorrWorld,
) -> None:
    item_id = awaiting(world)
    with frozen_today("2026-10-23"):
        with pytest.raises(ItemBackdatedError):
            world.answer_technical(item_id, answer="Fine.", answered_on="2026-10-21")
        with pytest.raises(ItemBackdatedError):
            world.answer_technical(item_id, answer="Fine.", answered_on="2026-10-24")
        world.answer_technical(
            item_id,
            answer="Fine.",
            answered_on="2026-10-21",
            date_reason="the email came Wednesday",
        )
    [answered] = payloads(world, item_id, "Technical.Answered")
    assert (answered["answered_on"], answered["date_reason"]) == (
        "2026-10-21",
        "the email came Wednesday",
    )
    [clock] = world.clocks("P123-RFI-0001")
    assert clock.closed_on == "2026-10-21"
    assert world.technical("P123-RFI-0001").item.responded_on == "2026-10-21"


def test_the_item_that_carries_the_answer_is_linked_and_named(world: CorrWorld) -> None:
    item_id = awaiting(world)
    letter = world.forge_item("P123-COR-0001", subject="Client reply", state="Received")
    with frozen_today("2026-10-22"):
        world.answer_technical(item_id, answer="See the letter.", answer_item_id=letter)
    data = world.technical("P123-RFI-0001").data
    assert data.answer_item_id == letter
    [link] = world.rows("SELECT to_id, relation, note FROM cur_links WHERE from_id = :f", f=item_id)
    assert (link["to_id"], link["relation"], link["note"]) == (letter, "references", "the answer")
    [responded] = payloads(world, item_id, "Correspondence.Responded")
    assert responded["response_id"] == letter
    [clock] = world.clocks("P123-RFI-0001")
    assert clock.state == "met"


def test_the_answering_revision_is_linked_when_it_is_a_document_revision(
    world: CorrWorld, tmp_path: Any
) -> None:
    docs = DocumentsWorld(world.db, tmp_path / "docs")
    with cf.system_view():
        docs.register("ISO-9001", title="Isometric")
        docs.create_revision("ISO-9001")
        revision = docs.revision("ISO-9001", "A").id
    letter = world.forge_item("P123-COR-0001", state="Received")
    item_id = awaiting(world)
    with frozen_today("2026-10-22"):
        with pytest.raises(InvalidItemError, match="not a document revision"):
            world.answer_technical(item_id, answering_revision_id=letter)
        world.answer_technical(item_id, answer="Re-issued.", answering_revision_id=revision)
    data = world.technical("P123-RFI-0001").data
    assert data.answering_revision_id == revision
    [link] = world.rows("SELECT to_id, note FROM cur_links WHERE from_id = :f", f=item_id)
    assert (link["to_id"], link["note"]) == (revision, "the answering revision")


def test_an_answer_that_names_something_unusable_is_refused_before_any_write(
    world: CorrWorld,
) -> None:
    item_id = awaiting(world)
    foreign = world.forge_technical("P123-RFI-0050", scope="project:OTHER")
    secret = world.forge_item("P123-COR-0003", state="Received", confidentiality="restricted")
    before = count_events(world)
    with frozen_today("2026-10-22"):
        for target, error in (
            (item_id, InvalidItemError),
            (foreign, RecordNotFoundError),
            (secret, RecordNotFoundError),
            ("01J000000000000000000000", RecordNotFoundError),
        ):
            with pytest.raises(error):
                world.answer_technical(item_id, answer_item_id=target)
        with pytest.raises(RecordNotFoundError):
            world.answer_technical(item_id, answering_revision_id="01J000000000000000000000")
    assert count_events(world) == before
    assert world.technical("P123-RFI-0001").item.state == "Awaiting response"


def _name(world: CorrWorld, item_id: str, *accounts: str) -> None:
    for account in accounts:
        world.forge_item_event(
            item_id,
            "Correspondence.ClearanceGranted",
            {"account": account, "granted_on": MONDAY, "reason": "counsel"},
        )


def test_the_answer_may_not_be_a_record_some_reader_of_the_item_cannot_read(
    world: CorrWorld,
) -> None:
    """The events of the item name the answering record, and every reader of the item reads them."""
    internal = world.forge_technical("P123-RFI-0040", state="Awaiting response")
    restricted = world.forge_technical(
        "P123-RFI-0041", state="Awaiting response", confidentiality="restricted"
    )
    open_letter = world.forge_item("P123-COR-0040", state="Received")
    restricted_letter = world.forge_item(
        "P123-COR-0041", state="Received", confidentiality="restricted"
    )
    secret_letter = world.forge_item(
        "P123-COR-0042", state="Received", confidentiality="privileged"
    )
    _name(world, secret_letter, "user:ctl")
    before = count_events(world)
    with frozen_today(MONDAY), cf.use_viewer(CONTROLLER):
        for rfi, letter in ((internal, restricted_letter), (internal, secret_letter),
                            (restricted, secret_letter)):  # fmt: skip
            with pytest.raises(RecordNotFoundError, match="no record"):
                world.answer_technical(rfi, answer_item_id=letter)
        assert count_events(world) == before  # nothing was written
        world.answer_technical(restricted, answer_item_id=restricted_letter)  # same class: fine
    with frozen_today(MONDAY), cf.use_viewer(CONTROLLER):
        world.answer_technical(internal, answer_item_id=open_letter)
    assert world.technical("P123-RFI-0040").data.answer_item_id == open_letter


def test_a_privileged_answer_must_be_readable_by_everyone_named_on_the_privileged_item(
    world: CorrWorld,
) -> None:
    rfi = world.forge_technical(
        "P123-RFI-0042", state="Awaiting response", confidentiality="privileged"
    )
    _name(world, rfi, "user:ctl", "user:amy")
    narrow = world.forge_item("P123-COR-0043", state="Received", confidentiality="privileged")
    _name(world, narrow, "user:ctl")  # amy could not read it
    wide = world.forge_item("P123-COR-0044", state="Received", confidentiality="privileged")
    _name(world, wide, "user:ctl", "user:amy", "user:bob")
    with frozen_today(MONDAY), cf.use_viewer(CONTROLLER):
        with pytest.raises(RecordNotFoundError):
            world.answer_technical(rfi, answer_item_id=narrow)
        world.answer_technical(rfi, answer_item_id=wide)


def test_the_answering_revision_may_not_be_above_the_class_of_the_item(
    world: CorrWorld, tmp_path: Any
) -> None:
    docs = DocumentsWorld(world.db, tmp_path / "docs")
    with cf.system_view():
        docs.register("ISO-9001", title="Isometric")
        docs.create_revision("ISO-9001")
        open_revision = docs.revision("ISO-9001", "A").id
        docs.register("ISO-9002", title="Commercial terms", confidentiality="restricted")
        docs.create_revision("ISO-9002")
        restricted_revision = docs.revision("ISO-9002", "A").id
    rfi = world.forge_technical("P123-RFI-0043", state="Awaiting response")
    with frozen_today(MONDAY), cf.use_viewer(CONTROLLER):
        with pytest.raises(RecordNotFoundError, match="no record"):
            world.answer_technical(rfi, answering_revision_id=restricted_revision)
        world.answer_technical(rfi, answering_revision_id=open_revision)


@pytest.mark.parametrize(
    "fields",
    [{"answer": ""}, {"answer": "  \n"}, {"cost_impact": "maybe"}, {"schedule_impact": "Yes"}],
)
def test_an_answer_without_text_or_with_a_wrong_flag_is_refused(
    world: CorrWorld, fields: dict[str, str]
) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY), pytest.raises(ValidationError):
        world.answer_technical(item_id, **fields)


def test_only_an_item_awaiting_a_response_is_answered(world: CorrWorld) -> None:
    draft = world.forge_technical("P123-RFI-0010")
    answered = world.forge_technical("P123-RFI-0011", state="Answered")
    with frozen_today(MONDAY):
        for target in (draft, answered):
            with pytest.raises(ItemStateError):
                world.answer_technical(target)
        with pytest.raises(RecordNotFoundError):
            world.answer_technical("01J000000000000000000000")


# --- ReviewTechnicalAnswer ------------------------------------------------------------------


def test_the_raiser_accepts_the_answer(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today("2026-10-22"):
        world.answer_technical(item_id, answer="Fine.")
    with frozen_today("2026-10-23"):
        done = world.review_technical(item_id, "accepted", note="thanks")
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Accepted"
    assert (row.data.review_decision, row.data.reviewed_on, row.data.review_note) == (
        "accepted",
        "2026-10-23",
        "thanks",
    )
    assert done.version == row.item.version
    [moved] = payloads(world, item_id, "Workflow.Transitioned")[-1:]
    assert (moved["transition"], moved["reason"]) == ("accept", "thanks")


def test_a_rejection_needs_a_note_and_an_acceptance_does_not(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY):
        world.answer_technical(item_id, answer="Fine.")
        before = count_events(world)
        for note in (None, "", "   "):
            with pytest.raises(InvalidItemError, match="say why"):
                world.review_technical(item_id, "rejected", note=note)
        assert count_events(world) == before
        world.review_technical(item_id, "rejected", note="does not answer the clash")
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Rejected" and row.data.review_decision == "rejected"
    other = awaiting(world, subject="Second question")
    with frozen_today(MONDAY):
        world.answer_technical(other, answer="Fine.")
        world.review_technical(other, "accepted")
    assert world.technical("P123-RFI-0002").item.state == "Accepted"


def test_only_an_answered_item_is_judged_and_the_decision_is_one_of_two(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY):
        with pytest.raises(ItemStateError):
            world.review_technical(item_id, "accepted")
        world.answer_technical(item_id, answer="Fine.")
        with pytest.raises(ValidationError):
            world.review_technical(item_id, "maybe")
        world.review_technical(item_id, "accepted")
        with pytest.raises(ItemStateError):
            world.review_technical(item_id, "accepted")


# --- ReissueTechnical -----------------------------------------------------------------------


def test_a_rejected_item_goes_round_again_and_the_old_answer_leaves_the_current_state(
    world: CorrWorld,
) -> None:
    item_id = awaiting(world)
    letter = world.forge_item("P123-COR-0001", state="Received")
    with frozen_today("2026-10-22"):
        world.answer_technical(
            item_id, answer="Not sure.", cost_impact="yes", answer_item_id=letter
        )
        world.review_technical(item_id, "rejected", note="does not answer the clash")
        world.reissue_technical(item_id, reason="clarified the question")
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Internal review"
    data = row.data
    assert (data.answer, data.answered_on, data.answer_cost_impact) == (None, None, None)
    assert (data.answer_schedule_impact, data.answer_item_id) == (None, None)
    assert (data.review_decision, data.reviewed_on, data.review_note) == (None, None, None)
    [reissued] = payloads(world, item_id, "Technical.Reissued")
    assert reissued == {"reason": "clarified the question", "round": 2}
    assert len(payloads(world, item_id, "Technical.Answered")) == 1  # the events keep the answer
    [moved] = payloads(world, item_id, "Workflow.Transitioned")[-1:]
    assert (moved["transition"], moved["reason"]) == ("reissue", "clarified the question")


def test_the_second_round_is_issued_answered_and_counted(world: CorrWorld) -> None:
    item_id = awaiting(world)
    letter = world.forge_item("P123-COR-0001", state="Received")
    with frozen_today("2026-10-22"):
        world.answer_technical(item_id, answer="One.", answer_item_id=letter)
        world.review_technical(item_id, "rejected", note="no")
        world.reissue_technical(item_id, reason="again")
    with frozen_today("2026-10-23"), cf.use_viewer(CONTROLLER):
        world.issue_technical(item_id)
    with frozen_today("2026-10-26"):
        world.answer_technical(item_id, answer="Two.", answer_item_id=letter)
        world.review_technical(item_id, "rejected", note="still no")
        world.reissue_technical(item_id, reason="third time")
    assert [p["round"] for p in payloads(world, item_id, "Technical.Reissued")] == [2, 3]
    links = world.rows("SELECT to_id FROM cur_links WHERE from_id = :f", f=item_id)
    assert len(links) == 1  # the same answer item is linked once
    assert len(world.clocks("P123-RFI-0001")) == 2
    row = world.technical("P123-RFI-0001")
    assert (row.item.state, row.item.issued_on) == ("Internal review", "2026-10-23")


def test_a_reissue_needs_a_rejected_item_and_a_reason(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY):
        with pytest.raises(ItemStateError):
            world.reissue_technical(item_id, reason="x")
        world.answer_technical(item_id, answer="Fine.")
        with pytest.raises(ItemStateError):
            world.reissue_technical(item_id, reason="x")
        world.review_technical(item_id, "rejected", note="no")
        for blank in ("", "  "):
            with pytest.raises(ValidationError):
                world.reissue_technical(item_id, reason=blank)
        world.reissue_technical(item_id, reason="again")
        with pytest.raises(ItemStateError):
            world.reissue_technical(item_id, reason="again")


# --- CloseTechnical -------------------------------------------------------------------------


def test_an_accepted_item_closes_without_a_reason(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today("2026-10-22"):
        world.answer_technical(item_id, answer="Fine.")
        world.review_technical(item_id, "accepted")
    with frozen_today("2026-10-23"):
        done = world.close_technical(item_id)
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Closed" and row.item.closed is True
    assert done.version == row.item.version
    [clock] = world.clocks("P123-RFI-0001")
    assert clock.state == "met"  # the answer met it; closing cancels only what is open


def test_an_item_still_waiting_closes_with_a_reason_and_its_clock_is_cancelled(
    world: CorrWorld,
) -> None:
    item_id = awaiting(world)
    with frozen_today("2026-10-24"):
        for blank in (None, "", "   "):
            with pytest.raises(ItemStateError, match="give the reason for closing"):
                world.close_technical(item_id, reason=blank)
        world.close_technical(item_id, reason="the designer withdrew the drawing")
    assert world.technical("P123-RFI-0001").item.state == "Closed"
    [clock] = world.clocks("P123-RFI-0001")
    assert (clock.state, clock.closed_on, clock.closed_reason) == (
        "cancelled",
        "2026-10-24",
        "the designer withdrew the drawing",
    )
    [moved] = payloads(world, item_id, "Workflow.Transitioned")[-1:]
    assert (moved["transition"], moved["reason"]) == (
        "close",
        "the designer withdrew the drawing",
    )


def test_a_rejected_item_closes_with_a_reason(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY):
        world.answer_technical(item_id, answer="Fine.")
        world.review_technical(item_id, "rejected", note="no")
        with pytest.raises(ItemStateError, match="give the reason"):
            world.close_technical(item_id)
        world.close_technical(item_id, reason="overtaken by events")
    assert world.technical("P123-RFI-0001").item.state == "Closed"


@pytest.mark.parametrize("state", ["Draft", "Internal review", "Issued", "Answered"])
def test_no_other_state_is_closed(world: CorrWorld, state: str) -> None:
    item_id = world.forge_technical("P123-RFI-0020", state=state)
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.close_technical(item_id, reason="x")


def test_a_closed_item_takes_no_more(world: CorrWorld) -> None:
    item_id = awaiting(world)
    with frozen_today(MONDAY):
        world.close_technical(item_id, reason="not needed")
        for command in (
            lambda: world.close_technical(item_id, reason="again"),
            lambda: world.answer_technical(item_id),
            lambda: world.update_technical(item_id, discipline="piping"),
        ):
            with pytest.raises(ItemStateError, match="takes no more changes"):
                command()


class _Recorder:
    """A constraint sink that keeps what it was told."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str | None]] = []

    def rfi_issued(self, uow: object, item: Any, data: Any) -> None:
        self.calls.append(("issued", item.number, item.state, data.answered_on))

    def rfi_answered(self, uow: object, item: Any, data: Any) -> None:
        self.calls.append(("answered", item.number, item.state, data.answered_on))


def test_the_constraint_hook_hears_of_the_issue_and_of_the_answer_with_the_item_as_it_is_then(
    world: CorrWorld,
) -> None:
    recorder = _Recorder()
    item_id = review(world)
    with constraints.use_sink(recorder), frozen_today(MONDAY):
        assert recorder.calls == []
        with cf.use_viewer(CONTROLLER):
            world.issue_technical(item_id)
        assert recorder.calls == [("issued", "P123-RFI-0001", "Awaiting response", None)]
        world.answer_technical(item_id, answer="Fine.")
    assert recorder.calls[1:] == [("answered", "P123-RFI-0001", "Answered", MONDAY)]


def test_a_refused_command_does_not_tell_the_hook(world: CorrWorld) -> None:
    recorder = _Recorder()
    draft = world.forge_technical("P123-RFI-0030")
    with constraints.use_sink(recorder), frozen_today(MONDAY):
        with pytest.raises(ItemStateError):
            world.issue_technical(draft)
        with pytest.raises(ItemStateError):
            world.answer_technical(draft)
    assert recorder.calls == []
