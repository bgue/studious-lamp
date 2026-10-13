"""Transmittal commands against a real ledger on every adapter (T08a)."""

from __future__ import annotations

from typing import Any

import pytest
from docworld import BASE, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import DuplicateKeyError, NoNumberingPatternError
from tl_mod_documents import registry
from tl_mod_documents.errors import (
    BackdatedError,
    InvalidTransmittalError,
    ProjectScopeError,
    RevisionNotFoundError,
    TransmittalNotFoundError,
    TransmittalStateError,
)
from tl_mod_documents.handlers.common import today
from tl_mod_documents.handlers.transmittals import (
    CloseTransmittal,
    CreateTransmittal,
    IssueTransmittal,
    RecordTransmittalResponse,
    VoidTransmittal,
    handle_close_transmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
    handle_record_transmittal_response,
    handle_void_transmittal,
)

SITE = {"name": "Site document control", "organisation": "Acme Construction", "email": None}


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


def create(world: World, revisions: list[str], **more: Any) -> Any:
    fields: dict[str, Any] = {
        "number": "P123-TRN-0001",
        "subject": "Isometrics for construction",
        "purpose": "for_construction",
        "recipients": [SITE],
        "revision_ids": revisions,
    }
    fields.update(more)
    return run(world, handle_create_transmittal, CreateTransmittal(**{**BASE, **fields}))


def transmittal(world: World, number: str = "P123-TRN-0001") -> registry.TransmittalRow:
    with open_uow(world.db, readonly=True) as uow:
        found = registry.find_transmittal(uow.conn(), "project:P123", number)
    assert found is not None
    return found


def items(world: World, number: str = "P123-TRN-0001") -> list[registry.TransmittalItemRow]:
    row = transmittal(world, number)
    with open_uow(world.db, readonly=True) as uow:
        return registry.transmittal_items(uow.conn(), row.id)


@pytest.fixture
def issued(world: World) -> World:
    """Two documents with an issued revision each: ISO-1234@A (IFR) and PID-0001@A (IFC)."""
    world.issued_document("ISO-1234", "IFR")
    world.issued_document("PID-0001", "IFC")
    return world


def rev_id(world: World, number: str, code: str = "A") -> str:
    return world.revision(number, code).id


def test_a_draft_transmittal_lists_its_revisions_and_recipients(issued: World) -> None:
    made = create(
        issued,
        [rev_id(issued, "ISO-1234"), rev_id(issued, "PID-0001")],
        due_date="2026-10-27",
        notes="Please acknowledge",
    )
    assert made.key == "P123-TRN-0001"
    assert [e.event_type for e in made.events] == ["Record.Created", "Transmittal.Defined"]
    row = transmittal(issued)
    assert (
        row.state == "Draft" and row.direction == "outgoing" and row.purpose == "for_construction"
    )
    assert row.title == "Isometrics for construction" and row.description == "Please acknowledge"
    assert row.due_date == "2026-10-27" and row.issued_on is None and row.item_count == 2
    assert row.recipients == [SITE]
    first, second = items(issued)
    assert (first.position, first.document_number, first.revision_code) == (1, "ISO-1234", "A")
    assert (first.issue_status, second.document_number, second.issue_status) == (
        "IFR",
        "PID-0001",
        "IFC",
    )


def test_the_number_is_allocated_when_none_is_typed(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")], number=None)
    assert made.key == "P123-TRN-0001"
    assert transmittal(issued, "P123-TRN-0001").number == "P123-TRN-0001"
    second = create(issued, [rev_id(issued, "ISO-1234")], number=None, subject="Again")
    assert second.key == "P123-TRN-0002"


def test_a_typed_number_cannot_be_used_twice(issued: World) -> None:
    create(issued, [rev_id(issued, "ISO-1234")])
    with pytest.raises(DuplicateKeyError):
        create(issued, [rev_id(issued, "ISO-1234")])


def test_a_superseded_revision_can_still_be_sent(issued: World) -> None:
    old = rev_id(issued, "ISO-1234")
    issued.create_revision("ISO-1234")
    issued.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    issued.issue("ISO-1234", "B", "IFR")  # supersedes A
    assert issued.revision("ISO-1234", "A").state == "Superseded"
    create(issued, [old, rev_id(issued, "ISO-1234", "B")])
    assert [i.revision_code for i in items(issued)] == ["A", "B"]


def test_only_issued_revisions_can_be_sent(issued: World) -> None:
    issued.create_revision("ISO-1234")  # B is a draft
    with pytest.raises(InvalidTransmittalError, match="issued revisions only.*ISO-1234@B is Draft"):
        create(issued, [rev_id(issued, "ISO-1234", "B")])


def test_a_revision_is_listed_once_and_must_exist_in_the_scope(issued: World) -> None:
    a = rev_id(issued, "ISO-1234")
    with pytest.raises(InvalidTransmittalError, match="only once"):
        create(issued, [a, a])
    with pytest.raises(RevisionNotFoundError):
        create(issued, [a, "nope"])
    with pytest.raises(RevisionNotFoundError):
        create(issued, [a], scope="project:P999")


def test_transmittals_belong_to_a_project(issued: World) -> None:
    with pytest.raises(ProjectScopeError):
        create(issued, [rev_id(issued, "ISO-1234")], scope="company")


def test_the_command_checks_its_own_fields(issued: World) -> None:
    a = rev_id(issued, "ISO-1234")
    good: dict[str, Any] = {
        **BASE,
        "number": "TRN-9",
        "subject": "s",
        "purpose": "for_review",
        "recipients": [SITE],
        "revision_ids": [a],
    }
    CreateTransmittal(**good)
    for bad in (
        {"subject": "  "},
        {"purpose": "for_fun"},
        {"direction": "sideways"},
        {"recipients": []},
        {"recipients": [{"name": " "}]},
        {"recipients": [{"name": "x", "colour": "red"}]},
        {"recipients": [SITE] * 101},
        {"revision_ids": []},
        {"revision_ids": ["r"] * 201},
        {"due_date": "tomorrow"},
        {"number": "N" * 129},
        {"notes": "n" * 10_001},
        {"origin": "import"},
    ):
        with pytest.raises(ValidationError):
            CreateTransmittal(**{**good, **bad})


def test_issuing_a_draft_moves_it_to_issued_and_records_the_date(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    result = run(
        issued,
        handle_issue_transmittal,
        IssueTransmittal(
            **BASE,
            stream_id=made.stream_id,
            issued_on="2026-10-12",
            date_reason="sent by courier the day before it was entered",
        ),
    )
    assert [e.event_type for e in result.events] == ["Transmittal.Issued", "Workflow.Transitioned"]
    assert (
        result.events[0].payload["date_reason"] == "sent by courier the day before it was entered"
    )
    row = transmittal(issued)
    assert row.state == "Issued" and row.issued_on == "2026-10-12"
    with pytest.raises(TransmittalStateError, match="only be issued while Draft"):
        run(issued, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))


def test_issuing_defaults_to_today_and_checks_the_version(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    with pytest.raises(ConcurrencyError):
        run(
            issued,
            handle_issue_transmittal,
            IssueTransmittal(**BASE, stream_id=made.stream_id, expected_version=1),
        )
    run(issued, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))
    assert len(transmittal(issued).issued_on or "") == 10


def test_the_answer_acknowledges_an_issued_transmittal(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    answer = RecordTransmittalResponse(
        **BASE,
        stream_id=made.stream_id,
        response_code="approved_with_comments",
        response_note="See markup",
    )
    with pytest.raises(TransmittalStateError, match="only be answered while Issued"):
        run(issued, handle_record_transmittal_response, answer)  # still a draft
    run(issued, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))
    result = run(issued, handle_record_transmittal_response, answer)
    assert [e.event_type for e in result.events] == [
        "Transmittal.ResponseRecorded",
        "Workflow.Transitioned",
    ]
    row = transmittal(issued)
    assert row.state == "Acknowledged"
    assert (row.response_code, row.response_note) == ("approved_with_comments", "See markup")
    assert row.responded_on is not None
    with pytest.raises(TransmittalStateError):
        run(issued, handle_record_transmittal_response, answer)  # answered once
    with pytest.raises(ValidationError):
        RecordTransmittalResponse(**BASE, stream_id=made.stream_id, response_code="maybe")  # type: ignore[arg-type]


def test_an_issued_or_answered_transmittal_can_be_closed(issued: World) -> None:
    first = create(issued, [rev_id(issued, "ISO-1234")])
    second = create(issued, [rev_id(issued, "PID-0001")], number="P123-TRN-0002")
    for made in (first, second):
        run(issued, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))
    run(
        issued,
        handle_record_transmittal_response,
        RecordTransmittalResponse(**BASE, stream_id=second.stream_id, response_code="approved"),
    )
    for made, number in ((first, "P123-TRN-0001"), (second, "P123-TRN-0002")):
        result = run(
            issued,
            handle_close_transmittal,
            CloseTransmittal(**BASE, stream_id=made.stream_id, reason="done"),
        )
        assert [e.event_type for e in result.events] == ["Workflow.Transitioned"]
        assert transmittal(issued, number).state == "Closed"
    with pytest.raises(TransmittalStateError, match="only be closed while Issued or Acknowledged"):
        run(issued, handle_close_transmittal, CloseTransmittal(**BASE, stream_id=first.stream_id))


def test_a_draft_cannot_be_closed_and_an_issued_one_cannot_be_voided(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    with pytest.raises(TransmittalStateError):
        run(issued, handle_close_transmittal, CloseTransmittal(**BASE, stream_id=made.stream_id))
    run(issued, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))
    with pytest.raises(TransmittalStateError, match="only be voided while Draft"):
        run(
            issued,
            handle_void_transmittal,
            VoidTransmittal(**BASE, stream_id=made.stream_id, reason="x"),
        )


def test_a_draft_can_be_voided_and_then_takes_no_more(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    result = run(
        issued,
        handle_void_transmittal,
        VoidTransmittal(**BASE, stream_id=made.stream_id, reason="drafted in error"),
    )
    assert [e.event_type for e in result.events] == ["Workflow.Transitioned", "Record.Voided"]
    row = transmittal(issued)
    assert row.state == "Void" and row.voided
    for handler, command in (
        (handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id)),
        (
            handle_void_transmittal,
            VoidTransmittal(**BASE, stream_id=made.stream_id, reason="again"),
        ),
    ):
        with pytest.raises(TransmittalStateError, match="Void"):
            run(issued, handler, command)
    with open_uow(issued.db, readonly=True) as uow:
        assert registry.list_transmittals(uow.conn(), "project:P123") == []  # a void one is hidden
        assert [
            t.number for t in registry.list_transmittals(uow.conn(), "project:P123", state="Void")
        ] == ["P123-TRN-0001"]


def test_a_transmittal_of_another_scope_or_unknown_is_not_found(issued: World) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    for stream in (made.stream_id, "nope"):
        with pytest.raises(TransmittalNotFoundError):
            run(
                issued,
                handle_issue_transmittal,
                IssueTransmittal(**{**BASE, "scope": "project:P999"}, stream_id=stream),
            )


def test_a_revision_voided_after_drafting_stops_the_issue(issued: World) -> None:
    """A transmittal checks its revisions again when it is issued."""
    from tl_core.ledger import NewEvent

    made = create(issued, [rev_id(issued, "ISO-1234")])
    a = issued.revision("ISO-1234", "A")
    with open_uow(issued.db) as uow:  # forge the state a future command could produce
        uow.append(
            stream_id=a.id,
            stream_type="documents.Revision",
            scope="project:P123",
            expected_version=a.version,
            events=[NewEvent(event_type="Record.Voided", payload={"reason": "forged"})],
            actor="user:u",
            source="test",
            correlation_id="c",
        )
    with pytest.raises(InvalidTransmittalError, match="issued revisions only"):
        run(issued, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))
    assert transmittal(issued).state == "Draft"


def test_without_a_number_or_pattern_the_creation_is_refused(issued: World) -> None:
    from tl_core.numbering.config import NumberingRegistry, use_numbering

    with use_numbering(NumberingRegistry([])):
        with pytest.raises(NoNumberingPatternError):
            create(issued, [rev_id(issued, "ISO-1234")], number=None)


def test_an_issue_or_answer_date_is_today_unless_a_reason_backs_an_earlier_one(
    issued: World,
) -> None:
    made = create(issued, [rev_id(issued, "ISO-1234")])
    for day in ("2999-01-01", "2026-10-12"):  # the future; an earlier day without a reason
        with pytest.raises(BackdatedError):
            run(
                issued,
                handle_issue_transmittal,
                IssueTransmittal(**BASE, stream_id=made.stream_id, issued_on=day),
            )
    assert transmittal(issued).state == "Draft"
    run(
        issued,
        handle_issue_transmittal,
        IssueTransmittal(**BASE, stream_id=made.stream_id, issued_on=today()),
    )
    for day in ("2999-01-01", "2026-10-12"):
        with pytest.raises(BackdatedError):
            run(
                issued,
                handle_record_transmittal_response,
                RecordTransmittalResponse(
                    **BASE, stream_id=made.stream_id, response_code="noted", responded_on=day
                ),
            )
    result = run(
        issued,
        handle_record_transmittal_response,
        RecordTransmittalResponse(
            **BASE,
            stream_id=made.stream_id,
            response_code="noted",
            responded_on="2026-10-12",
            date_reason="phoned through, entered next day",
        ),
    )
    assert result.events[0].payload["date_reason"] == "phoned through, entered next day"
    assert transmittal(issued).responded_on == "2026-10-12"


def test_a_typed_number_must_fit_the_projects_transmittal_pattern(issued: World) -> None:
    a = rev_id(issued, "ISO-1234")
    for number in ("TRN-0001", "P999-TRN-0001", "P123-DWG-0001", "P123-TRN-1", "P123-TRN-00001"):
        with pytest.raises(InvalidTransmittalError, match="does not fit"):
            create(issued, [a], number=number)
    assert create(issued, [a], number="P123-TRN-0007").key == "P123-TRN-0007"
