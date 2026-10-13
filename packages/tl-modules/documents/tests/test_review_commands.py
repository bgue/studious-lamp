"""Review cycle commands against a real ledger on every adapter (T08b)."""

from __future__ import annotations

from typing import Any

import pytest
from docworld import BASE, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import UnsupportedRecordTypeError
from tl_mod_documents import registry
from tl_mod_documents.errors import (
    DocumentClosedError,
    InvalidReviewError,
    NoRenditionError,
    NotYourReviewError,
    RenditionNotAllowedError,
    ReviewNotFoundError,
    ReviewStateError,
    RevisionNotFoundError,
    RevisionStateError,
)
from tl_mod_documents.handlers.reviews import (
    CloseReviewCycle,
    OpenReviewCycle,
    OverrideReviewOutcome,
    RecordReviewOutcome,
    RecordReviewOutcomeOnBehalf,
    ReviewerRequest,
    handle_close_review_cycle,
    handle_open_review_cycle,
    handle_override_review_outcome,
    handle_record_review_outcome,
    handle_record_review_outcome_on_behalf,
)
from tl_mod_documents.handlers.revisions import VoidRevision, handle_void_revision


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


def open_review(world: World, number: str = "ISO-1234", code: str = "A", **more: Any) -> Any:
    fields: dict[str, Any] = {
        "revision_id": world.revision(number, code).id,
        "reviewers": [{"reviewer": "user:ana"}, {"reviewer": "user:bo", "due_date": "2026-10-18"}],
        "due_date": "2026-10-20",
    }
    fields.update(more)
    return run(world, handle_open_review_cycle, OpenReviewCycle(**{**BASE, **fields}))


def answer(
    world: World, cycle: str, reviewer: str, outcome: Any, comment: str | None = None
) -> Any:
    return run(
        world,
        handle_record_review_outcome,
        RecordReviewOutcome(
            **{**BASE, "actor": reviewer}, review_cycle_id=cycle, outcome=outcome, comment=comment
        ),
    )


def close(world: World, cycle: str, **more: Any) -> Any:
    return run(
        world, handle_close_review_cycle, CloseReviewCycle(**BASE, review_cycle_id=cycle, **more)
    )


def cycles(
    world: World, number: str = "ISO-1234", code: str = "A"
) -> list[registry.ReviewCycleRow]:
    rev = world.revision(number, code)
    with open_uow(world.db, readonly=True) as uow:
        return registry.review_cycles_of(uow.conn(), rev.id)


def reviewers(world: World, cycle_id: str) -> list[registry.ReviewerRow]:
    with open_uow(world.db, readonly=True) as uow:
        return registry.reviewers_of(uow.conn(), cycle_id)


@pytest.fixture
def draft(world: World) -> World:
    """ISO-1234 registered with draft revision A and a PDF."""
    world.people("u", "ana", "bo", "cy", "zed")
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    return world


def test_opening_a_review_puts_the_revision_and_a_new_document_in_review(draft: World) -> None:
    result = open_review(draft)
    assert [e.event_type for e in result.events] == [
        "Record.Created",
        "ReviewCycle.Defined",
        "Workflow.Transitioned",  # the revision
        "Workflow.Transitioned",  # the document
    ]
    assert result.key == "ISO-1234@A/RC1"
    assert draft.revision("ISO-1234", "A").state == "In Review"
    assert draft.document("ISO-1234").state == "In Review"
    (cycle,) = cycles(draft)
    assert (cycle.round, cycle.state, cycle.due_date, cycle.outcome) == (
        1,
        "open",
        "2026-10-20",
        None,
    )
    assert cycle.title == "Review of ISO-1234@A, round 1"
    ana, bo = reviewers(draft, cycle.id)
    assert (ana.reviewer, ana.due_date, ana.outcome) == ("user:ana", "2026-10-20", None)
    assert bo.due_date == "2026-10-18"


def test_a_review_needs_a_draft_with_no_review_open(draft: World) -> None:
    open_review(draft)
    with pytest.raises(RevisionStateError, match="In Review; only a draft can be sent for review"):
        open_review(draft)
    # the revision cannot be issued while it is in review
    with pytest.raises(RevisionStateError, match="close its review first"):
        draft.issue("ISO-1234", "A")


def test_a_reviewer_is_listed_once_and_the_command_checks_its_fields(draft: World) -> None:
    with pytest.raises(InvalidReviewError, match="only once"):
        open_review(draft, reviewers=[{"reviewer": "user:ana"}, {"reviewer": " user:ana "}])
    rev = draft.revision("ISO-1234", "A").id
    for bad in (
        {"reviewers": []},
        {"reviewers": [{"reviewer": " "}]},
        {"reviewers": [{"reviewer": "x", "colour": "red"}]},
        {"reviewers": [{"reviewer": f"r{i}"} for i in range(51)]},
        {"due_date": "soon"},
        {"reviewers": [{"reviewer": "x", "due_date": "2026-13-01"}]},
    ):
        fields = {"revision_id": rev, "reviewers": [{"reviewer": "user:ana"}], **bad}
        with pytest.raises(ValidationError):
            OpenReviewCycle(**BASE, **fields)
    assert draft.revision("ISO-1234", "A").state == "Draft"  # nothing was written


def test_a_review_of_an_unknown_revision_or_a_closed_document_is_refused(draft: World) -> None:
    with pytest.raises(RevisionNotFoundError):
        run(
            draft,
            handle_open_review_cycle,
            OpenReviewCycle(
                **BASE, revision_id="nope", reviewers=[ReviewerRequest(reviewer="user:ana")]
            ),
        )
    from tl_mod_documents.handlers.documents import VoidDocument, handle_void_document

    doc = draft.document("ISO-1234")
    run(draft, handle_void_document, VoidDocument(**BASE, stream_id=doc.id, reason="x"))
    with pytest.raises(DocumentClosedError):
        open_review(draft)


def test_each_reviewer_answers_once(draft: World) -> None:
    cycle = open_review(draft).stream_id
    result = answer(draft, cycle, "user:ana", "approved_with_comments", "Check the weld map")
    assert [e.event_type for e in result.events] == ["ReviewCycle.OutcomeRecorded"]
    ana, bo = reviewers(draft, cycle)
    assert (ana.outcome, ana.comment) == ("approved_with_comments", "Check the weld map")
    assert ana.responded_on is not None and bo.outcome is None
    with pytest.raises(ReviewStateError, match="user:ana has already answered"):
        answer(draft, cycle, "user:ana", "approved")
    with pytest.raises(InvalidReviewError, match="'user:zed' is not a reviewer"):
        answer(draft, cycle, "user:zed", "approved")
    with pytest.raises(ValidationError):
        RecordReviewOutcome(**{**BASE, "actor": "user:bo"}, review_cycle_id=cycle, outcome="shrug")  # type: ignore[arg-type]
    with pytest.raises(ConcurrencyError):
        run(
            draft,
            handle_record_review_outcome,
            RecordReviewOutcome(
                **{**BASE, "actor": "user:bo"},
                review_cycle_id=cycle,
                outcome="approved",
                expected_version=1,
            ),
        )


def test_closing_takes_the_worst_answer_and_sends_the_revision_back_to_draft(draft: World) -> None:
    cycle = open_review(draft).stream_id
    answer(draft, cycle, "user:ana", "approved")
    answer(draft, cycle, "user:bo", "approved_with_comments")
    result = close(draft, cycle)
    assert [e.event_type for e in result.events] == [
        "ReviewCycle.Closed",
        "Workflow.Transitioned",  # the revision, back to Draft
        "Workflow.Transitioned",  # the document, back to Registered (no issued revision yet)
    ]
    (row,) = cycles(draft)
    assert (row.state, row.outcome) == ("closed", "approved_with_comments")
    assert row.closed_on is not None
    assert draft.revision("ISO-1234", "A").state == "Draft"
    assert draft.document("ISO-1234").state == "Registered"
    with pytest.raises(ReviewStateError, match="already closed"):
        close(draft, cycle)
    with pytest.raises(ReviewStateError, match="is closed"):
        answer(draft, cycle, "user:ana", "approved")


def test_one_rejection_rejects_the_cycle(draft: World) -> None:
    cycle = open_review(draft).stream_id
    answer(draft, cycle, "user:ana", "approved")
    answer(draft, cycle, "user:bo", "rejected", "Wrong line class")
    close(draft, cycle)
    assert cycles(draft)[0].outcome == "rejected"


def test_closing_early_needs_a_reason_and_an_unanswered_round_is_withdrawn(draft: World) -> None:
    cycle = open_review(draft).stream_id
    with pytest.raises(InvalidReviewError, match="user:ana, user:bo have not answered"):
        close(draft, cycle)
    with pytest.raises(InvalidReviewError, match="nobody has answered"):
        close(draft, cycle, reason="Review withdrawn", outcome="approved")
    close(draft, cycle, reason="Review withdrawn")  # withdrawn: counts as rejected
    assert cycles(draft)[0].outcome == "rejected"


def test_a_partial_close_takes_the_outcome_of_those_who_answered(draft: World) -> None:
    cycle = open_review(draft).stream_id
    answer(draft, cycle, "user:ana", "approved")
    close(draft, cycle, reason="Bo is on leave")
    assert cycles(draft)[0].outcome == "approved"


def test_a_second_round_numbers_on_and_the_revision_can_then_be_issued(draft: World) -> None:
    first = open_review(draft).stream_id
    answer(draft, first, "user:ana", "rejected")
    answer(draft, first, "user:bo", "rejected")
    close(draft, first)
    second = open_review(draft, reviewers=[{"reviewer": "user:ana"}])
    assert second.key == "ISO-1234@A/RC2"
    assert [c.round for c in cycles(draft)] == [1, 2]
    answer(draft, second.stream_id, "user:ana", "approved")
    close(draft, second.stream_id)
    draft.issue("ISO-1234", "A", "IFR")  # the draft returned from review can be issued
    assert draft.document("ISO-1234").state == "Issued"


def test_a_review_of_a_later_revision_leaves_an_issued_document_issued(draft: World) -> None:
    draft.issue("ISO-1234", "A", "IFR")
    draft.create_revision()
    draft.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    cycle = open_review(draft, code="B").stream_id
    assert draft.revision("ISO-1234", "B").state == "In Review"
    assert draft.document("ISO-1234").state == "Issued"
    answer(draft, cycle, "user:ana", "approved")
    answer(draft, cycle, "user:bo", "approved")
    close(draft, cycle)
    assert draft.document("ISO-1234").state == "Issued"
    assert draft.revision("ISO-1234", "B").state == "Draft"


def test_during_a_review_only_markups_can_be_added(draft: World) -> None:
    rev = draft.revision("ISO-1234", "A")
    early = draft.upload(rev.id, "pdf", b"%PDF-1.7 changed", "changed.pdf")  # uploaded in Draft
    open_review(draft)
    draft.attach("ISO-1234", "A", slot="markup", data=b"%PDF markup", name="m.pdf")
    from tl_mod_documents.handlers.renditions import AttachRendition, handle_attach_rendition

    with pytest.raises(RenditionNotAllowedError, match="In Review; it accepts markup"):
        run(
            draft,
            handle_attach_rendition,
            AttachRendition(**BASE, revision_id=rev.id, file_id=early.file_id),
        )
    with pytest.raises(UnsupportedRecordTypeError, match="takes markup"):  # and not uploaded either
        draft.upload(rev.id, "pdf", b"%PDF-1.7 later", "later.pdf")


def test_a_revision_in_review_cannot_be_voided(draft: World) -> None:
    open_review(draft)
    rev = draft.revision("ISO-1234", "A")
    with pytest.raises(RevisionStateError, match="close its review first"):
        run(draft, handle_void_revision, VoidRevision(**BASE, stream_id=rev.id, reason="x"))


def test_a_cycle_of_another_scope_or_unknown_is_not_found(draft: World) -> None:
    cycle = open_review(draft).stream_id
    for stream in (cycle, "nope"):
        with pytest.raises(ReviewNotFoundError):
            run(
                draft,
                handle_close_review_cycle,
                CloseReviewCycle(**{**BASE, "scope": "project:P999"}, review_cycle_id=stream),
            )


def test_issuing_still_needs_a_rendition_after_a_review(world: World) -> None:
    world.people("u", "ana", "bo")
    world.register()
    world.create_revision()
    cycle = open_review(world).stream_id
    answer(world, cycle, "user:ana", "approved")
    answer(world, cycle, "user:bo", "approved")
    close(world, cycle)
    with pytest.raises(NoRenditionError):
        world.issue("ISO-1234", "A")


def test_reviewers_are_people_with_an_account_and_not_only_the_author(draft: World) -> None:
    for name in ("user:nobody", "ana", "agent:ana", "user:"):
        with pytest.raises(InvalidReviewError, match="not an active person account"):
            open_review(draft, reviewers=[{"reviewer": name}])
    with pytest.raises(InvalidReviewError, match="at least one other reviewer"):
        open_review(draft, reviewers=[{"reviewer": "user:u"}])  # u wrote the revision
    assert cycles(draft) == []
    made = open_review(draft, reviewers=[{"reviewer": " user:U "}, {"reviewer": "user:ana"}])
    assert [r.reviewer for r in reviewers(draft, made.stream_id)] == ["user:u", "user:ana"]


def test_a_reviewer_answers_for_themselves_only(draft: World) -> None:
    cycle = open_review(draft).stream_id
    with pytest.raises(NotYourReviewError, match="user:u cannot answer for user:ana"):
        run(
            draft,
            handle_record_review_outcome,
            RecordReviewOutcome(
                **BASE, review_cycle_id=cycle, reviewer="user:ana", outcome="approved"
            ),
        )
    with pytest.raises(InvalidReviewError, match="'user:u' is not a reviewer"):
        answer(draft, cycle, "user:u", "approved")  # the caller must be a reviewer of the cycle
    assert [r.outcome for r in reviewers(draft, cycle)] == [None, None]


def test_an_admin_records_an_answer_on_behalf_with_a_comment_and_the_event_says_so(
    draft: World,
) -> None:
    cycle = open_review(draft).stream_id
    with pytest.raises(ValidationError):
        RecordReviewOutcomeOnBehalf(
            **BASE, review_cycle_id=cycle, reviewer="user:ana", outcome="approved", comment=" "
        )
    result = run(
        draft,
        handle_record_review_outcome_on_behalf,
        RecordReviewOutcomeOnBehalf(
            **{**BASE, "actor": "user:boss"},
            review_cycle_id=cycle,
            reviewer="user:ana",
            outcome="approved",
            comment="Ana replied by mail on the 12th",
        ),
    )
    payload = result.events[0].payload
    assert (payload["reviewer"], payload["recorded_by"]) == ("user:ana", "user:boss")
    assert result.events[0].actor == "user:boss"
    ana, _ = reviewers(draft, cycle)
    assert ana.outcome == "approved"
    with pytest.raises(ReviewStateError, match="already answered"):
        answer(draft, cycle, "user:ana", "rejected")
    own = answer(draft, cycle, "user:bo", "approved")
    assert own.events[0].payload["recorded_by"] is None


def test_only_an_admin_closes_with_an_outcome_milder_than_the_worst_answer(draft: World) -> None:
    cycle = open_review(draft).stream_id
    answer(draft, cycle, "user:ana", "rejected", "Wrong line class")
    answer(draft, cycle, "user:bo", "approved")
    with pytest.raises(InvalidReviewError, match="only an admin can close it as approved"):
        close(draft, cycle, outcome="approved")
    with pytest.raises(ValidationError):
        OverrideReviewOutcome(**BASE, review_cycle_id=cycle, outcome="approved", reason=" ")
    assert cycles(draft)[0].state == "open"
    result = run(
        draft,
        handle_override_review_outcome,
        OverrideReviewOutcome(
            **{**BASE, "actor": "user:boss"},
            review_cycle_id=cycle,
            outcome="approved_with_comments",
            reason="Rejection withdrawn after the call on the 12th",
        ),
    )
    closed = result.events[0].payload
    assert (closed["outcome"], closed["worst_answer"]) == ("approved_with_comments", "rejected")
    assert closed["reason"] == "Rejection withdrawn after the call on the 12th"
    assert cycles(draft)[0].outcome == "approved_with_comments"
    assert draft.revision("ISO-1234", "A").state == "Draft"
    with pytest.raises(ReviewStateError, match="already closed"):
        close(draft, cycle, outcome="rejected")


def test_a_person_may_close_with_a_stricter_outcome_than_the_answers(draft: World) -> None:
    cycle = open_review(draft).stream_id
    answer(draft, cycle, "user:ana", "approved")
    answer(draft, cycle, "user:bo", "approved")
    close(draft, cycle, outcome="rejected")
    assert cycles(draft)[0].outcome == "rejected"
