"""Revision commands against a real ledger (T04, T05): create to void, and the invariant."""

from __future__ import annotations

import random
from typing import Any

import pytest
from docworld import BASE, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.ledger import ConcurrencyError
from tl_mod_documents import registry
from tl_mod_documents.errors import (
    InvalidIssueStatusError,
    InvalidRevisionCodeError,
    NoRenditionError,
    OpenRevisionError,
    RevisionNotFoundError,
    RevisionStateError,
)
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    SupersedeRevision,
    VoidRevision,
    handle_issue_revision,
    handle_supersede_revision,
    handle_void_revision,
)
from tl_mod_documents.invariants import check_document


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


def sound(world: World, number: str = "ISO-1234") -> None:
    doc = world.document(number)
    with open_uow(world.db, readonly=True) as uow:
        assert check_document(uow.conn(), doc.id) == []


def test_the_first_revision_takes_the_first_code_of_the_scheme_and_is_a_draft(world: World) -> None:
    world.register()
    made = world.create_revision(purpose="First issue for review", intended_status="IFR")
    assert made.key == "ISO-1234@A"
    rev = world.revision("ISO-1234", "A")
    assert rev.state == "Draft" and rev.ordinal == 1 and rev.previous_revision_id is None
    assert rev.purpose == "First issue for review" and rev.intended_status == "IFR"
    assert not rev.issued and not rev.is_current and rev.issue_status is None
    assert rev.title == "ISO-1234 rev A"
    sound(world)


def test_a_new_revision_waits_until_the_open_one_is_issued_or_voided(world: World) -> None:
    world.register()
    world.create_revision()
    with pytest.raises(OpenRevisionError, match="revision A of ISO-1234 is still Draft"):
        world.create_revision()
    rev = world.revision("ISO-1234", "A")
    run(
        world,
        handle_void_revision,
        VoidRevision(**BASE, stream_id=rev.id, reason="started in error"),
    )
    made = world.create_revision()
    assert made.key == "ISO-1234@B"  # a void revision keeps its code
    assert [r.ordinal for r in world.revisions("ISO-1234")] == [1, 2]
    sound(world)


def test_codes_follow_the_scheme_and_only_go_forward(world: World) -> None:
    world.register("DS-0001", doc_type="DS")  # staged
    assert world.create_revision("DS-0001").key == "DS-0001@P1"
    world.attach("DS-0001", "P1")
    world.issue("DS-0001", "P1")
    assert world.create_revision("DS-0001").key == "DS-0001@P2"
    world.attach("DS-0001", "P2", data=b"%PDF-1.7 p2", name="p2.pdf")
    world.issue("DS-0001", "P2")
    assert world.create_revision("DS-0001", stage="C").key == "DS-0001@C1"
    with pytest.raises(OpenRevisionError):
        world.create_revision("DS-0001")


def test_an_explicit_code_must_belong_to_the_scheme_and_come_after_the_last(world: World) -> None:
    world.register()
    with pytest.raises(InvalidRevisionCodeError, match="not a code of the alpha scheme"):
        world.create_revision(code="1")
    with pytest.raises(InvalidRevisionCodeError, match="not a code of the alpha scheme"):
        world.create_revision(code="I")
    with pytest.raises(InvalidRevisionCodeError, match="a code or a stage"):
        world.create_revision(code="B", stage="C")
    world.create_revision(code="C")  # a document may start anywhere in the scheme
    world.attach("ISO-1234", "C")
    world.issue("ISO-1234", "C")
    with pytest.raises(InvalidRevisionCodeError, match="does not come after"):
        world.create_revision(code="B")
    assert world.create_revision(code="E").key == "ISO-1234@E"


def test_the_command_checks_its_own_fields(world: World) -> None:
    world.register()
    doc = world.document("ISO-1234")
    with pytest.raises(ValidationError):
        CreateRevision(**BASE, document_id=doc.id, revision_date="13/10/2026")
    with pytest.raises(ValidationError):
        CreateRevision(**BASE, document_id=doc.id, revision_date="2026-02-30")
    for absurd in ("2999-01-01", "1900-01-01"):
        with pytest.raises(ValidationError, match="revision_date"):
            CreateRevision(**BASE, document_id=doc.id, revision_date=absurd)
    with pytest.raises(ValidationError):
        CreateRevision(**BASE, document_id=doc.id, code="X" * 200)
    with pytest.raises(InvalidIssueStatusError):
        world.create_revision(intended_status="NOPE")


def test_issuing_needs_a_pdf_or_native_rendition(world: World) -> None:
    world.register()
    world.create_revision()
    with pytest.raises(NoRenditionError):
        world.issue("ISO-1234", "A")
    world.attach("ISO-1234", "A", slot="markup")  # a markup is not a copy to issue
    with pytest.raises(NoRenditionError):
        world.issue("ISO-1234", "A")
    world.attach("ISO-1234", "A", slot="native", data=b"native bytes", name="a.dwg")
    world.issue("ISO-1234", "A")  # a native copy is enough


def test_issuing_makes_the_revision_current_and_the_document_follows(world: World) -> None:
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    result = world.issue(
        "ISO-1234", "A", "IFR", issued_on="2026-10-10", date_reason="issued by post on the 10th"
    )
    assert [e.event_type for e in result.events] == [
        "Revision.Issued",
        "Workflow.Transitioned",
        "Document.CurrentRevisionChanged",
        "Workflow.Transitioned",
    ]
    rev = world.revision("ISO-1234", "A")
    assert rev.state == "Issued" and rev.is_current and rev.issue_status == "IFR"
    assert rev.status_class == "review" and rev.issued_on == "2026-10-10"
    doc = world.document("ISO-1234")
    assert doc.state == "Issued"
    assert (doc.current_revision_code, doc.current_revision_status) == ("A", "IFR")
    assert doc.current_revision_class == "review" and doc.current_revision_issued_on == "2026-10-10"
    sound(world)


def test_an_issue_status_that_is_not_in_the_file_is_refused(world: World) -> None:
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    with pytest.raises(InvalidIssueStatusError):
        world.issue("ISO-1234", "A", "XYZ")
    assert world.revision("ISO-1234", "A").state == "Draft"


def test_only_a_draft_can_be_issued_and_only_once(world: World) -> None:
    world.issued_document()
    with pytest.raises(RevisionStateError, match="only a draft can be issued"):
        world.issue("ISO-1234", "A")


def test_one_current_revision_per_status_class(world: World) -> None:
    world.issued_document(status="IFR")  # A: review
    world.create_revision()
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")  # B: construction; A stays current in review
    a, b = world.revision("ISO-1234", "A"), world.revision("ISO-1234", "B")
    assert a.is_current and a.state == "Issued" and b.is_current
    assert world.document("ISO-1234").current_revision_code == "B"
    sound(world)

    world.create_revision()
    world.attach("ISO-1234", "C", data=b"%PDF-1.7 c", name="c.pdf")
    result = world.issue("ISO-1234", "C", "IFR")  # C: review, so A is superseded
    a, b, c = (world.revision("ISO-1234", x) for x in "ABC")
    assert (a.state, a.is_current, a.superseded_by) == ("Superseded", False, c.id)
    assert b.is_current and b.state == "Issued" and c.is_current
    assert world.document("ISO-1234").current_revision_code == "C"
    assert "Revision.Superseded" in [e.event_type for e in result.events]
    sound(world)


def test_supersede_ends_an_issued_current_revision_and_the_document_falls_back(
    world: World,
) -> None:
    world.issued_document(status="IFR")  # A
    world.create_revision()
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")  # B is the document's current
    a, b = world.revision("ISO-1234", "A"), world.revision("ISO-1234", "B")
    # B cannot be superseded by an earlier revision
    with pytest.raises(RevisionStateError, match="not a later issued revision"):
        run(
            world,
            handle_supersede_revision,
            SupersedeRevision(**BASE, stream_id=b.id, superseded_by_id=a.id, reason="x"),
        )
    # A (review class) is superseded by B explicitly
    run(
        world,
        handle_supersede_revision,
        SupersedeRevision(**BASE, stream_id=a.id, superseded_by_id=b.id, reason="IFC replaces IFR"),
    )
    a = world.revision("ISO-1234", "A")
    assert a.state == "Superseded" and not a.is_current and a.superseded_by == b.id
    assert world.document("ISO-1234").current_revision_code == "B"  # unchanged
    # a record-class revision issued later becomes the document's current
    world.create_revision()
    world.attach("ISO-1234", "C", data=b"%PDF-1.7 c", name="c.pdf")
    world.issue("ISO-1234", "C", "ASB")
    assert world.document("ISO-1234").current_revision_code == "C"  # the newest current one
    sound(world)


def test_a_superseded_or_draft_revision_cannot_be_superseded(world: World) -> None:
    world.issued_document()
    world.create_revision()
    a, b = world.revision("ISO-1234", "A"), world.revision("ISO-1234", "B")
    with pytest.raises(RevisionStateError, match="only an issued, current revision"):
        run(
            world,
            handle_supersede_revision,
            SupersedeRevision(**BASE, stream_id=b.id, superseded_by_id=a.id, reason="x"),
        )


def test_void_is_for_a_draft_that_was_never_issued(world: World) -> None:
    world.issued_document()
    a = world.revision("ISO-1234", "A")
    with pytest.raises(RevisionStateError, match="only a draft can be voided"):
        run(world, handle_void_revision, VoidRevision(**BASE, stream_id=a.id, reason="x"))
    world.create_revision()
    b = world.revision("ISO-1234", "B")
    result = run(world, handle_void_revision, VoidRevision(**BASE, stream_id=b.id, reason="oops"))
    assert [e.event_type for e in result.events] == ["Workflow.Transitioned", "Record.Voided"]
    voided = world.revision("ISO-1234", "B")
    assert voided.state == "Void" and voided.voided
    with pytest.raises(RevisionStateError):
        run(world, handle_void_revision, VoidRevision(**BASE, stream_id=b.id, reason="again"))
    sound(world)


def test_a_stale_version_is_a_concurrency_error(world: World) -> None:
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    a = world.revision("ISO-1234", "A")
    with pytest.raises(ConcurrencyError):
        run(
            world,
            handle_issue_revision,
            IssueRevision(**BASE, stream_id=a.id, expected_version=1, issue_status="IFR"),
        )


def test_a_revision_of_another_scope_or_unknown_is_not_found(world: World) -> None:
    world.issued_document()
    a = world.revision("ISO-1234", "A")
    for stream in (a.id, "nope"):
        with pytest.raises(RevisionNotFoundError):
            run(
                world,
                handle_void_revision,
                VoidRevision(**{**BASE, "scope": "project:P999"}, stream_id=stream, reason="x"),
            )


def test_the_invariant_holds_after_any_sequence_of_commands(world: World) -> None:
    rng = random.Random(7)
    world.register()
    statuses = ["IFR", "IFA", "IFC", "AFC", "ASB"]
    made = 0
    for step in range(10):
        rev = None
        with open_uow(world.db, readonly=True) as uow:
            rev = registry.open_revision(uow.conn(), world.document("ISO-1234").id)
        if rev is None:
            world.create_revision()
            made += 1
            continue
        if rng.random() < 0.2:
            run(world, handle_void_revision, VoidRevision(**BASE, stream_id=rev.id, reason="x"))
        else:
            world.attach("ISO-1234", rev.code, data=f"%PDF-1.7 {step}".encode(), name=f"{step}.pdf")
            world.issue("ISO-1234", rev.code, rng.choice(statuses))
        sound(world)
    assert made >= 3


def test_the_issue_date_is_today_never_future_and_a_past_date_needs_a_reason(world: World) -> None:
    from datetime import date, timedelta

    from tl_mod_documents.errors import BackdatedError

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    with pytest.raises(BackdatedError, match="in the future"):
        world.issue("ISO-1234", "A", "IFR", issued_on=tomorrow)
    with pytest.raises(BackdatedError, match="give the reason for the date"):
        world.issue("ISO-1234", "A", "IFR", issued_on=yesterday)
    with pytest.raises(BackdatedError, match="give the reason"):
        world.issue("ISO-1234", "A", "IFR", issued_on=yesterday, date_reason="   ")
    assert world.revision("ISO-1234", "A").state == "Draft"
    result = world.issue("ISO-1234", "A", "IFR", issued_on=today)  # today needs no reason
    issued = result.events[0].payload
    assert issued["issued_on"] == today and issued["date_reason"] is None
