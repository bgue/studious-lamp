"""Which generic commands reach a documents record (ADR-0010 addendum, L-P1-I1-8).

The envelope and the typed fields of a module record change only through the module's own
commands. Each record type's allow-list is stated in ``module.py``; this test pins it from the
outside, through the real handlers, so a handler that forgets ``require_generic_command`` fails
here.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.files.service import RegisterUpload
from tl_core.modules import GENERIC_COMMANDS
from tl_core.services.commands import UpdateRecord, VoidRecord
from tl_core.services.errors import UnknownPsetError, UnsupportedRecordTypeError
from tl_core.services.links import AddLink, SuggestLink, handle_add_link, handle_suggest_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_update_record, handle_void_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_documents.module import (
    DOCUMENT_GENERIC_COMMANDS,
    REVISION_GENERIC_COMMANDS,
    TRANSMITTAL_GENERIC_COMMANDS,
    spec,
)
from tl_mod_documents.names import RECORD_TYPES


@pytest.fixture
def ids(world: World) -> dict[str, str]:
    """A document, a revision and a rendition, by record type."""
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
    return {
        "documents.Document": world.document("ISO-1234").id,
        "documents.Revision": rev.id,
        "documents.Rendition": rendition_id,
    }


def attempt(world: World, command: str, record_id: str) -> None:
    """Run the generic ``command`` against a record; an unsupported type raises."""
    with open_uow(world.db) as uow:
        row = (
            uow.conn()
            .exec_driver_sql("SELECT version FROM cur_core_record WHERE id = '" + record_id + "'")
            .scalar_one()
        )
        version = int(row)
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
            target = (
                uow.conn()
                .exec_driver_sql("SELECT id FROM cur_core_record WHERE key = '47-FV-9999'")
                .scalar_one()
            )
            cls: Any = AddLink if command == "AddLink" else SuggestLink
            handler: Any = handle_add_link if command == "AddLink" else handle_suggest_link
            handler(uow, cls(**BASE, from_id=record_id, to_id=target, relation="references"))
        elif command == "AttachFile":
            from tl_core.files.service import FileService  # the check is in the service

            service: FileService = world.files
            service.register_upload(
                uow,
                RegisterUpload(
                    **BASE,
                    record_id=record_id,
                    slot=None,
                    filename="a.txt",
                    content_type="text/plain",
                    size=1,
                    sha256=hashlib.sha256(b"a").hexdigest(),
                ),
            )
        else:  # pragma: no cover - a new generic command must be listed here on purpose
            raise AssertionError(f"unknown generic command {command}")


ALLOWED = {
    "documents.Document": DOCUMENT_GENERIC_COMMANDS,
    "documents.Revision": REVISION_GENERIC_COMMANDS,
    "documents.Rendition": frozenset(),
}


@pytest.mark.parametrize("command", sorted(GENERIC_COMMANDS))
@pytest.mark.parametrize("record_type", sorted(ALLOWED))
def test_each_generic_command_on_each_type_follows_the_allow_list(
    world: World, ids: dict[str, str], record_type: str, command: str
) -> None:
    world.tag("47-FV-9999")  # a link target
    if command in ALLOWED[record_type]:
        # allowed: the command gets past the allow-list and fails (or not) for its own reasons
        try:
            attempt(world, command, ids[record_type])
        except UnsupportedRecordTypeError as exc:  # pragma: no cover - the failure being tested
            pytest.fail(f"{command} on {record_type} should be allowed: {exc}")
        except UnknownPsetError:
            pass  # SetPsetValues reached the pset lookup
    else:
        with pytest.raises(
            UnsupportedRecordTypeError, match=f"{command} cannot change a {record_type}"
        ):
            attempt(world, command, ids[record_type])


def test_the_spec_lists_exactly_the_allow_lists_above() -> None:
    allowed = spec().generic_commands
    assert allowed["documents.Document"] == DOCUMENT_GENERIC_COMMANDS
    assert allowed["documents.Revision"] == REVISION_GENERIC_COMMANDS
    assert allowed["documents.Transmittal"] == TRANSMITTAL_GENERIC_COMMANDS
    assert set(allowed) == {"documents.Document", "documents.Revision", "documents.Transmittal"}
    assert RECORD_TYPES == spec().record_types


def test_no_record_type_allows_the_commands_that_change_its_meaning() -> None:
    """The title, the state and a void are never generic, whatever the type."""
    forbidden = {"UpdateRecord", "VoidRecord", "TransitionWorkflow"}
    for commands in spec().generic_commands.values():
        assert not (commands & forbidden)
