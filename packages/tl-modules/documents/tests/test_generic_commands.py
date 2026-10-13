"""Which generic commands reach a documents record, and when (ADR-0010 addendum, L-P1-I1-8).

The envelope and the typed fields of a module record change only through the module's own
commands. Each record type's allow-list is stated in ``module.py`` and the state guards in
``guards.py``; this test pins both from the outside, through the real handlers and the real file
service, for all five record types, so a handler that forgets ``require_generic`` fails here.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_core.modules import GENERIC_COMMANDS
from tl_core.services.commands import UpdateRecord, VoidRecord
from tl_core.services.errors import ServiceError, UnsupportedRecordTypeError
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
    handle_accept_link,
    handle_add_link,
    handle_decline_link,
    handle_flag_link,
    handle_repin_link,
    handle_retract_link,
    handle_suggest_link,
    handle_verify_link,
)
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_update_record, handle_void_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_documents.handlers.reviews import (
    OpenReviewCycle,
    ReviewerRequest,
    handle_open_review_cycle,
)
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    Recipient,
    handle_create_transmittal,
)
from tl_mod_documents.module import (
    DOCUMENT_GENERIC_COMMANDS,
    REVISION_GENERIC_COMMANDS,
    TRANSMITTAL_GENERIC_COMMANDS,
    spec,
)
from tl_mod_documents.names import RECORD_TYPES

LINK_LIFE = {
    "AcceptLink": (AcceptLink, handle_accept_link, {}),
    "DeclineLink": (DeclineLink, handle_decline_link, {}),
    "RepinLink": (RepinLink, handle_repin_link, {}),
    "VerifyLink": (VerifyLink, handle_verify_link, {}),
    "FlagLink": (FlagLink, handle_flag_link, {"status": "stale", "reason": "x"}),
    "RetractLink": (RetractLink, handle_retract_link, {"reason": "x"}),
}


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


@pytest.fixture
def ids(world: World) -> dict[str, str]:
    """One record of each of the five types, each made by its own command."""
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    rev = world.revision("ISO-1234", "A")
    (rendition_id,) = [
        r["id"]
        for r in world.rows(
            "SELECT id FROM cur_documents_rendition WHERE revision_id = :r", r=rev.id
        )
    ]
    doc = world.document("ISO-1234")
    world.people("u", "ana")
    world.issued_document("ISO-2000")  # a revision a transmittal can carry
    sent = run(
        world,
        handle_create_transmittal,
        CreateTransmittal(
            **BASE,
            subject="Isometrics to site",
            purpose="for_review",
            recipients=[Recipient(name="Site")],
            revision_ids=[world.revision("ISO-2000", "A").id],
        ),
    )
    review = run(
        world,
        handle_open_review_cycle,
        OpenReviewCycle(
            **BASE, revision_id=rev.id, reviewers=[ReviewerRequest(reviewer="user:ana")]
        ),
    )
    world.tag("47-FV-9999")  # a link target
    return {
        "documents.Document": doc.id,
        "documents.Revision": rev.id,
        "documents.Rendition": rendition_id,
        "documents.Transmittal": sent.stream_id,
        "documents.ReviewCycle": review.stream_id,
    }


def upload(world: World, record_id: str, slot: str | None, data: bytes = b"x") -> None:
    declared = RegisterUpload(
        **BASE,
        record_id=record_id,
        slot=slot,
        filename="a.pdf",
        content_type="application/pdf",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    with open_uow(world.db) as uow:
        ticket = world.files.register_upload(uow, declared)
    with open_uow(world.db) as uow:
        world.files.complete_upload(
            uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(data)
        )


def attempt(world: World, command: str, record_id: str, record_type: str) -> None:
    """Run the generic ``command`` against a record; a refusal raises."""
    version = int(world.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record_id))
    target = world.scalar("SELECT id FROM cur_core_record WHERE key = '47-FV-9999'")
    with open_uow(world.db) as uow:
        if command == "UpdateRecord":
            handle_update_record(
                uow,
                UpdateRecord(
                    **BASE, stream_id=record_id, expected_version=version, changes={"title": "x"}
                ),
            )
        elif command == "VoidRecord":
            handle_void_record(
                uow, VoidRecord(**BASE, stream_id=record_id, expected_version=version, reason="x")
            )
        elif command == "SetPsetValues":
            handle_set_pset_values(
                uow,
                SetPsetValues(
                    **BASE,
                    stream_id=record_id,
                    expected_version=version,
                    pset="no_such_pset",
                    layer="standard",
                    values={},
                ),
            )
        elif command == "TransitionWorkflow":
            handle_transition_workflow(
                uow,
                TransitionWorkflow(
                    **BASE, stream_id=record_id, expected_version=version, transition="void"
                ),
            )
        elif command in ("AddLink", "SuggestLink"):
            cls: Any = AddLink if command == "AddLink" else SuggestLink
            handler: Any = handle_add_link if command == "AddLink" else handle_suggest_link
            handler(uow, cls(**BASE, from_id=record_id, to_id=target, relation="references"))
        elif command == "AttachFile":
            slot = "markup" if record_type == "documents.Revision" else None
            world.files.register_upload(
                uow,
                RegisterUpload(
                    **BASE,
                    record_id=record_id,
                    slot=slot,
                    filename="a.txt",
                    content_type="application/pdf" if slot else "text/plain",
                    size=1,
                    sha256=hashlib.sha256(b"a").hexdigest(),
                ),
            )
        else:
            raise AssertionError(f"unknown generic command {command}")


def attempt_link_life(world: World, command: str, record_id: str) -> None:
    """Run a link-lifecycle command on a link that starts at the record."""
    target = world.scalar("SELECT id FROM cur_core_record WHERE key = '47-FV-9999'")
    link_id = world.link_from(record_id, target)
    cls, handler, extra = LINK_LIFE[command]
    with open_uow(world.db) as uow:
        handler(uow, cls(**BASE, link_id=link_id, **extra))


ALLOWED: dict[str, frozenset[str]] = {
    "documents.Document": DOCUMENT_GENERIC_COMMANDS,
    "documents.Revision": REVISION_GENERIC_COMMANDS,
    "documents.Rendition": frozenset(),
    "documents.Transmittal": TRANSMITTAL_GENERIC_COMMANDS,
    "documents.ReviewCycle": frozenset(),
}


@pytest.mark.parametrize("command", sorted(GENERIC_COMMANDS))
@pytest.mark.parametrize("record_type", sorted(ALLOWED))
def test_each_generic_command_on_each_type_follows_the_allow_list(
    world: World, ids: dict[str, str], record_type: str, command: str
) -> None:
    def run() -> None:
        if command in LINK_LIFE:
            attempt_link_life(world, command, ids[record_type])
        else:
            attempt(world, command, ids[record_type], record_type)

    if command in ALLOWED[record_type]:
        try:  # allowed: it gets past the allow-list and fails (or not) for its own reasons
            run()
        except UnsupportedRecordTypeError as exc:  # pragma: no cover - the failure being tested
            pytest.fail(f"{command} on {record_type} should be allowed: {exc}")
        except Exception as exc:  # noqa: BLE001 - any other refusal is the command's own rule
            assert not isinstance(exc, UnsupportedRecordTypeError)
    else:
        with pytest.raises(
            UnsupportedRecordTypeError, match=f"{command} cannot change a {record_type}"
        ):
            run()


def test_the_spec_lists_exactly_the_allow_lists_above() -> None:
    allowed = spec().generic_commands
    assert dict(allowed) == {k: v for k, v in ALLOWED.items() if v}
    assert RECORD_TYPES == spec().record_types == set(ALLOWED)


def test_no_record_type_allows_the_commands_that_change_its_meaning() -> None:
    """The title, the state and a void are never generic, whatever the type."""
    forbidden = {"UpdateRecord", "VoidRecord", "TransitionWorkflow"}
    for commands in spec().generic_commands.values():
        assert not (commands & forbidden)


# --- state guards ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "slot", "allowed"),
    [
        ("Draft", "native", True),
        ("Draft", "pdf", True),
        ("Draft", "markup", True),
        ("Draft", "signed", False),
        ("Draft", None, False),
        ("In Review", "pdf", False),
        ("In Review", "native", False),
        ("In Review", "markup", True),
        ("Issued", "pdf", False),
        ("Issued", "markup", True),
        ("Issued", "signed", True),
        ("Superseded", "native", False),
        ("Superseded", "signed", True),
        ("Void", "markup", False),
    ],
)
def test_what_a_revision_takes_as_an_upload_follows_its_state(
    world: World, state: str, slot: str | None, allowed: bool
) -> None:
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    rev = world.revision("ISO-1234", "A")
    if state == "In Review":
        world.move(rev.id, "start_review")
    elif state in ("Issued", "Superseded"):
        world.issue("ISO-1234", "A", "IFR")
        if state == "Superseded":
            world.move(rev.id, "supersede")
    elif state == "Void":
        world.move(rev.id, "void")
    if allowed:
        upload(world, rev.id, slot)
    else:
        with pytest.raises(UnsupportedRecordTypeError):
            upload(world, rev.id, slot)


@pytest.mark.parametrize("state", ["Draft", "Issued"])
def test_a_transmittal_takes_links_and_attachments_only_as_a_draft(
    world: World, ids: dict[str, str], state: str
) -> None:
    if state == "Issued":
        world.move(ids["documents.Transmittal"], "issue")
    for command in ("AddLink", "SuggestLink", "AttachFile"):
        if state == "Draft":
            try:
                attempt(world, command, ids["documents.Transmittal"], "documents.Transmittal")
            except UnsupportedRecordTypeError as exc:  # pragma: no cover
                pytest.fail(str(exc))
            except ServiceError:
                pass  # past the guard; a second link to the same record is a duplicate
        else:
            with pytest.raises(
                UnsupportedRecordTypeError, match="Issued transmittal takes no more"
            ):
                attempt(world, command, ids["documents.Transmittal"], "documents.Transmittal")
