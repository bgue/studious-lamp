"""Review commands: accept, return, void (P2-FORMS S3)."""

from __future__ import annotations

from typing import Any

import pytest
from forms_world import World
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.modules import require_generic
from tl_core.services.commands import UpdateRecord, VoidRecord
from tl_core.services.errors import RecordNotFoundError, UnsupportedRecordTypeError
from tl_core.services.records import handle_update_record, handle_void_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_forms.commands import ReturnFormSubmission
from tl_mod_forms.errors import MSG_SELF_REVIEW, MSG_UNKNOWN, FormStateError
from tl_mod_forms.guards import MSG_NOT_SUBMITTED, submitted_or_later
from tl_mod_forms.module import FORMS_GENERIC_COMMANDS


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def submitted(world: World, who: str = "uma") -> str:
    return str(world.submit(who=who, template=world.template()).stream_id)


def test_accept_by_a_controller_who_is_not_the_author(world: World) -> None:
    sub = submitted(world)
    made = world.call("bea", "AcceptFormSubmission", submission_id=sub, note="Fine")
    assert world.state(sub) == "Accepted" and made.version == world.version(sub)
    row = world.submission(sub)
    assert (row["reviewed_by"], row["review_note"]) == ("user:bea", "Fine")
    assert row["reviewed_on"] and world.events(sub, "Submission.Accepted")


def test_return_needs_a_note_and_sends_the_form_back(world: World) -> None:
    sub = submitted(world)
    with pytest.raises(ValidationError):
        ReturnFormSubmission(actor="user:bea", source="t", scope="project:P123", submission_id=sub)  # type: ignore[call-arg]
    world.call("bea", "ReturnFormSubmission", submission_id=sub, note="Add a count")
    assert world.state(sub) == "Returned"
    assert world.submission(sub)["review_note"] == "Add a count"


@pytest.mark.parametrize("name", ["AcceptFormSubmission", "ReturnFormSubmission"])
def test_the_author_is_refused_even_as_a_controller(world: World, name: str) -> None:
    sub = submitted(world, who="ada")
    extra = {"note": "x"} if name == "ReturnFormSubmission" else {}
    assert raises(ForbiddenError, world, "ada", name, submission_id=sub, **extra) == MSG_SELF_REVIEW
    assert world.state(sub) == "Submitted"


@pytest.mark.parametrize(
    ("name", "extra"),
    [
        ("AcceptFormSubmission", {}),
        ("ReturnFormSubmission", {"note": "x"}),
        ("VoidFormSubmission", {"reason": "x"}),
    ],
)
def test_a_user_holds_no_review_or_void_word(
    world: World, name: str, extra: dict[str, str]
) -> None:
    sub = submitted(world)
    with pytest.raises(ForbiddenError, match="controller access word"):
        world.call("rob", name, submission_id=sub, **extra)
    assert world.state(sub) == "Submitted"


def test_accept_and_return_take_a_submitted_form_only(world: World) -> None:
    sub = submitted(world)
    world.call("bea", "AcceptFormSubmission", submission_id=sub)
    for name, extra in (("AcceptFormSubmission", {}), ("ReturnFormSubmission", {"note": "x"})):
        assert "Accepted" in raises(FormStateError, world, "bea", name, submission_id=sub, **extra)
    draft = world.save(template=world.template()).stream_id
    own = world.save(who="ada", template=world.template()).stream_id
    assert "Draft" in raises(
        FormStateError, world, "ada", "AcceptFormSubmission", submission_id=own
    )
    assert (
        raises(RecordNotFoundError, world, "bea", "AcceptFormSubmission", submission_id=draft)
        == MSG_UNKNOWN
    )


@pytest.mark.parametrize("path", ["submitted", "accepted", "returned"])
def test_void_from_the_three_states_voids_the_record_too(world: World, path: str) -> None:
    sub = submitted(world)
    if path == "accepted":
        world.call("bea", "AcceptFormSubmission", submission_id=sub)
    if path == "returned":
        world.call("bea", "ReturnFormSubmission", submission_id=sub, note="x")
    made = world.call("bea", "VoidFormSubmission", submission_id=sub, reason="Wrong form")
    assert world.state(sub) == "Voided" and made.version == world.version(sub)
    assert world.submission(sub)["void_reason"] == "Wrong form"
    assert world.scalar("SELECT voided FROM cur_core_record WHERE id = :i", i=sub)
    kinds = [e["event_type"] for e in world.events(sub)][-3:]
    assert kinds == ["Submission.Voided", "Workflow.Transitioned", "Record.Voided"]
    assert "Voided" in raises(
        FormStateError, world, "bea", "VoidFormSubmission", submission_id=sub, reason="again"
    )


def test_void_is_refused_from_a_draft(world: World) -> None:
    own = world.save(who="ada", template=world.template()).stream_id
    assert "Draft" in raises(
        FormStateError, world, "ada", "VoidFormSubmission", submission_id=own, reason="x"
    )
    other = world.save(template=world.template()).stream_id  # another person's draft
    assert (
        raises(
            RecordNotFoundError, world, "bea", "VoidFormSubmission", submission_id=other, reason="x"
        )
        == MSG_UNKNOWN
    )


def test_transitions_are_by_module_only(world: World) -> None:
    sub = submitted(world)
    move = TransitionWorkflow(
        actor="user:bea", source="t", scope="project:P123", stream_id=sub,
        expected_version=world.version(sub), transition="accept", reason=None,
    )  # fmt: skip
    with pytest.raises(UnsupportedRecordTypeError), open_uow(world.db) as uow:
        handle_transition_workflow(uow, move)
    update = UpdateRecord(
        actor="user:bea", source="t", scope="project:P123", stream_id=sub,
        expected_version=world.version(sub), changes={"title": "x"},
    )  # fmt: skip
    with pytest.raises(UnsupportedRecordTypeError), open_uow(world.db) as uow:
        handle_update_record(uow, update)
    void = VoidRecord(
        actor="user:bea", source="t", scope="project:P123", stream_id=sub,
        expected_version=world.version(sub), reason="x",
    )  # fmt: skip
    with pytest.raises(UnsupportedRecordTypeError), open_uow(world.db) as uow:
        handle_void_record(uow, void)
    assert world.state(sub) == "Submitted"


def test_the_generic_commands_are_the_listed_ones_and_wait_for_a_submit(world: World) -> None:
    assert {"SetPsetValues", "AddLink", "AttachFile", "RetractLink"} <= FORMS_GENERIC_COMMANDS
    assert "UpdateRecord" not in FORMS_GENERIC_COMMANDS
    draft = world.save(template=world.template()).stream_id
    done = submitted(world)
    for name in sorted(FORMS_GENERIC_COMMANDS):
        with open_uow(world.db, readonly=True) as uow:
            conn = uow.conn()
            require_generic(conn, "forms.Submission", name, done, actor="user:uma")
            with (
                cf.use_viewer(cf.Viewer(actor="user:uma", account="user:uma")),
                pytest.raises(UnsupportedRecordTypeError, match=MSG_NOT_SUBMITTED),
            ):  # a draft is its author's alone (CR1)
                require_generic(conn, "forms.Submission", name, draft, actor="user:uma")
    world.call("bea", "VoidFormSubmission", submission_id=done, reason="x")
    with open_uow(world.db, readonly=True) as uow, pytest.raises(UnsupportedRecordTypeError):
        submitted_or_later(uow.conn(), done, None)


def test_the_envelope_row_of_a_voided_form_reads_voided(world: World) -> None:
    sub = submitted(world)
    world.call("bea", "VoidFormSubmission", submission_id=sub, reason="x")
    with open_uow(world.db, readonly=True) as uow:
        row = (
            uow.conn()
            .execute(text("SELECT status, voided FROM cur_core_record WHERE id = :i"), {"i": sub})
            .first()
        )
    assert row is not None and (row.status, bool(row.voided)) == ("Voided", True)
