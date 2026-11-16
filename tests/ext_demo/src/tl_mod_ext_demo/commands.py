"""The one command of ext_demo: add a note, with its confidentiality class."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from . import NOTE, NOTE_ADDED


class ExtDemoAddNote(Command):
    """Add a note to a project; ``note_class`` is fixed at add time (default internal)."""

    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=4000)
    note_class: Literal["internal", "restricted"] = "internal"


def handle_add_note(uow: UnitOfWork, cmd: ExtDemoAddNote) -> CommandResult:
    """Append ``Record.Created`` and ``Note.Added`` to a new stream; never commits."""
    return create_module_record(
        uow,
        cmd,
        record_type=NOTE,
        title=cmd.title,
        key=cmd.key,
        extra_events=[
            NewEvent(
                event_type=NOTE_ADDED,
                payload={"body": cmd.body, "note_class": cmd.note_class},
            )
        ],
    )
