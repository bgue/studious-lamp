"""The actions the documents module offers on a document, a revision and a transmittal (P1-UX2-S1).

The offered set is held to what the handlers do: each command of a record is run for real inside a
unit of work that is rolled back, and the commands the handlers do not refuse on state or access
grounds are compared with the offers. The readable cases then say it in words.
"""

from __future__ import annotations

from typing import Any

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.actions import Level, allowed_actions
from tl_core.services.commands import Command
from tl_mod_documents.actions import CARRIABLE, RULES, states_for
from tl_mod_documents.commands import API_COMMANDS
from tl_mod_documents.errors import (
    DocumentClosedError,
    InvalidTransmittalError,
    RevisionStateError,
    TransmittalStateError,
)
from tl_mod_documents.handlers.documents import (
    SupersedeDocument,
    VoidDocument,
    handle_void_document,
)
from tl_mod_documents.handlers.revisions import IssueRevision, SupersedeRevision, VoidRevision
from tl_mod_documents.handlers.transmittals import (
    CloseTransmittal,
    CreateTransmittal,
    IssueTransmittal,
    Recipient,
    RecordTransmittalResponse,
    VoidTransmittal,
    handle_close_transmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
    handle_record_transmittal_response,
    handle_void_transmittal,
)
from tl_mod_documents.names import REVISION, TRANSMITTAL

USER = cf.Viewer(actor="user:u", level=0, account="user:u")
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
VIEWERS: dict[str, tuple[cf.Viewer, Level]] = {
    "user": (USER, "user"),
    "controller": (CONTROLLER, "controller"),
    "admin": (CONTROLLER, "admin"),
}
RANK = {"user": 0, "controller": 1, "admin": 2}
ACCESS = {spec.model.__name__: spec.access for spec in API_COMMANDS}
HANDLER = {spec.model.__name__: spec.handler for spec in API_COMMANDS}
SITE = Recipient(name="Site document control", organisation="Acme Construction", email=None)
#: What a handler raises when the state of the record (or of its document) says no.
STATE_REFUSALS = (RevisionStateError, DocumentClosedError, TransmittalStateError)


def asked(world: World, record_id: str, who: str) -> list[str]:
    viewer, level = VIEWERS[who]
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        found = allowed_actions(
            uow,
            record_id,
            actor=viewer.actor,
            holds=lambda wanted: RANK[wanted] <= RANK[level],
        )
    return [a.command for a in found.actions]


class _Rollback(Exception):
    pass


class _Refused(Exception):
    pass


def unrefused(world: World, name: str, cmd: Command, who: str) -> bool:
    """True when ``cmd`` is not refused on the ground of state or access (the run is rolled back).

    The access word is the API gate's, so it is checked as the gate does; the handler then runs for
    real. A transmittal of a draft revision is refused as ``InvalidTransmittalError`` ("issued
    revisions only"), which for ``CreateTransmittal`` is the state refusal.
    """
    viewer, level = VIEWERS[who]
    if RANK[level] < RANK[ACCESS[name]]:
        return False
    refusals = (
        (*STATE_REFUSALS, InvalidTransmittalError)
        if name == "CreateTransmittal"
        else STATE_REFUSALS
    )
    try:
        with cf.use_viewer(viewer), open_uow(world.db) as uow:
            try:
                HANDLER[name](uow, cmd)
            except refusals as exc:
                # the replacement a person picks is data, like a reason: not the record's state
                if "not a later issued revision" not in str(exc):
                    raise _Refused from exc
            except Exception:  # noqa: BLE001 - any other refusal is about the data typed
                pass
            raise _Rollback
    except _Refused:
        return False
    except _Rollback:
        return True
    return True  # pragma: no cover


def commands_on(world: World, record_id: str, other_id: str) -> dict[str, Command]:
    """Every command of the table, aimed at ``record_id`` (``other_id`` is the other end)."""
    return {
        "SupersedeDocument": SupersedeDocument(
            **BASE, stream_id=record_id, superseded_by_id=other_id, reason="replaced"
        ),
        "VoidDocument": VoidDocument(**BASE, stream_id=record_id, reason="in error"),
        "IssueRevision": IssueRevision(**BASE, stream_id=record_id, issue_status="IFR"),
        "SupersedeRevision": SupersedeRevision(
            **BASE, stream_id=record_id, superseded_by_id=other_id, reason="replaced"
        ),
        "CreateTransmittal": CreateTransmittal(
            **BASE,
            subject="Isometrics",
            purpose="for_construction",
            recipients=[SITE],
            revision_ids=[record_id],
        ),
        "VoidRevision": VoidRevision(**BASE, stream_id=record_id, reason="in error"),
        "IssueTransmittal": IssueTransmittal(**BASE, stream_id=record_id),
        "RecordTransmittalResponse": RecordTransmittalResponse(
            **BASE, stream_id=record_id, response_code="approved"
        ),
        "CloseTransmittal": CloseTransmittal(**BASE, stream_id=record_id),
        "VoidTransmittal": VoidTransmittal(**BASE, stream_id=record_id, reason="in error"),
    }


def want_for(world: World, record_type: str, record_id: str, other_id: str, who: str) -> list[str]:
    cmds = commands_on(world, record_id, other_id)
    return [
        rule.command
        for rule in RULES
        if rule.record_type == record_type
        and unrefused(world, rule.command, cmds[rule.command], who)
    ]


# --- the table is the handlers' ----------------------------------------------------------------


def test_every_rule_names_a_command_of_the_module_with_the_same_access() -> None:
    for rule in RULES:
        assert rule.command in ACCESS, rule.command
        assert ACCESS[rule.command] == rule.level, rule.command


def test_the_states_come_from_the_table() -> None:
    assert states_for("IssueRevision", REVISION) == ("Draft",)
    assert states_for("CloseTransmittal", TRANSMITTAL) == ("Issued", "Acknowledged")
    assert CARRIABLE == states_for("CreateTransmittal", REVISION) == ("Issued", "Superseded")
    with pytest.raises(KeyError):
        states_for("IssueRevision", TRANSMITTAL)


# --- the world: a document with an issued revision A and a draft revision B ---------------------


@pytest.fixture
def docs(world: World) -> dict[str, str]:
    world.issued_document("ISO-1234", "IFR")
    world.create_revision("ISO-1234")  # B, a draft
    world.issued_document("PID-0001", "IFC")
    world.register("OLD-0001")
    world.create_revision("OLD-0001")  # a draft revision of a document that is then voided
    with open_uow(world.db) as uow:
        handle_void_document(
            uow, VoidDocument(**BASE, stream_id=world.document("OLD-0001").id, reason="in error")
        )
    return {
        "doc": world.document("ISO-1234").id,
        "A": world.revision("ISO-1234", "A").id,
        "B": world.revision("ISO-1234", "B").id,
        "other doc": world.document("PID-0001").id,
        "other": world.revision("PID-0001", "A").id,
        "void doc": world.document("OLD-0001").id,
        "void doc draft": world.revision("OLD-0001", "A").id,
    }


def test_a_draft_revision_offers_issue_to_a_controller_only(
    world: World, docs: dict[str, str]
) -> None:
    assert asked(world, docs["B"], "user") == ["VoidRevision"]
    assert asked(world, docs["B"], "controller") == ["IssueRevision", "VoidRevision"]
    assert asked(world, docs["B"], "admin") == ["IssueRevision", "VoidRevision"]


def test_an_issued_current_revision_offers_supersede_to_a_controller_and_a_transmittal(
    world: World, docs: dict[str, str]
) -> None:
    assert asked(world, docs["A"], "controller") == ["SupersedeRevision", "CreateTransmittal"]
    assert asked(world, docs["A"], "user") == ["CreateTransmittal"]


def test_a_superseded_revision_offers_only_a_transmittal(
    world: World, docs: dict[str, str]
) -> None:
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFR")  # supersedes A
    assert world.revision("ISO-1234", "A").state == "Superseded"
    assert asked(world, docs["A"], "admin") == ["CreateTransmittal"]
    assert asked(world, docs["B"], "controller") == ["SupersedeRevision", "CreateTransmittal"]


def test_an_open_document_offers_its_controlling_acts_to_a_controller_only(
    world: World, docs: dict[str, str]
) -> None:
    assert asked(world, docs["doc"], "controller") == ["SupersedeDocument", "VoidDocument"]
    assert asked(world, docs["doc"], "user") == []


def test_a_void_document_offers_nothing_and_neither_do_its_revisions(
    world: World, docs: dict[str, str]
) -> None:
    for who in ("user", "controller", "admin"):
        assert asked(world, docs["void doc"], who) == [], who
        assert asked(world, docs["void doc draft"], who) == [], who


@pytest.mark.parametrize("who", ["user", "controller", "admin"])
def test_the_offered_set_is_what_the_handlers_do_not_refuse(
    world: World, docs: dict[str, str], who: str
) -> None:
    other = docs["other doc"]
    for name, record_type in (("doc", "documents.Document"), ("void doc", "documents.Document")):
        assert asked(world, docs[name], who) == want_for(
            world, record_type, docs[name], other, who
        ), (name, who)
    other_revision = docs["other"]
    for name in ("A", "B", "void doc draft", "other"):
        assert asked(world, docs[name], who) == want_for(
            world, REVISION, docs[name], other_revision, who
        ), (name, who)


# --- transmittals ------------------------------------------------------------------------------


def make_transmittal(world: World, docs: dict[str, str], number: str, upto: str) -> str:
    """A transmittal of revision A taken as far as ``upto``: draft, issued, acknowledged, closed
    or void."""
    with open_uow(world.db) as uow:
        made = handle_create_transmittal(
            uow,
            CreateTransmittal(
                **BASE,
                number=number,
                subject="Isometrics",
                purpose="for_construction",
                recipients=[SITE],
                revision_ids=[docs["other"]],
            ),
        )
    steps: dict[str, list[tuple[Any, Command]]] = {
        "draft": [],
        "void": [
            (handle_void_transmittal, VoidTransmittal(**BASE, stream_id=made.stream_id, reason="x"))
        ],
        "issued": [(handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id))],
        "acknowledged": [
            (handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id)),
            (
                handle_record_transmittal_response,
                RecordTransmittalResponse(**BASE, stream_id=made.stream_id, response_code="noted"),
            ),
        ],
        "closed": [
            (handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=made.stream_id)),
            (handle_close_transmittal, CloseTransmittal(**BASE, stream_id=made.stream_id)),
        ],
    }
    for handler, cmd in steps[upto]:
        with open_uow(world.db) as uow:
            handler(uow, cmd)
    return made.stream_id


STATES = ("draft", "issued", "acknowledged", "closed", "void")


@pytest.fixture
def transmittals(world: World, docs: dict[str, str]) -> dict[str, str]:
    return {
        state: make_transmittal(world, docs, f"P123-TRN-{n:04d}", state)
        for n, state in enumerate(STATES, start=1)
    }


def test_a_draft_transmittal_is_issued_by_a_controller_and_an_issued_one_is_answered_or_closed(
    world: World, transmittals: dict[str, str]
) -> None:
    assert asked(world, transmittals["draft"], "user") == ["VoidTransmittal"]
    assert asked(world, transmittals["draft"], "controller") == [
        "IssueTransmittal",
        "VoidTransmittal",
    ]
    assert asked(world, transmittals["issued"], "user") == [
        "RecordTransmittalResponse",
        "CloseTransmittal",
    ]
    assert asked(world, transmittals["issued"], "admin") == [
        "RecordTransmittalResponse",
        "CloseTransmittal",
    ]
    assert asked(world, transmittals["acknowledged"], "user") == ["CloseTransmittal"]
    for state in ("closed", "void"):
        assert asked(world, transmittals[state], "admin") == [], state


@pytest.mark.parametrize("who", ["user", "controller", "admin"])
@pytest.mark.parametrize("state", STATES)
def test_the_offered_transmittal_set_is_what_the_handlers_do_not_refuse(
    world: World, docs: dict[str, str], transmittals: dict[str, str], state: str, who: str
) -> None:
    record_id = transmittals[state]
    assert asked(world, record_id, who) == want_for(
        world, TRANSMITTAL, record_id, docs["other"], who
    )
