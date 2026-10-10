"""One atomic edit of a record: field changes and pset batches in a single unit of work (P0-I3-T00).

A form save used to send an `UpdateRecord` and then one `SetPsetValues` per (pset, layer). A
failure in the middle left the earlier commands applied. `handle_edit_record` runs the same
handlers one after the other inside the caller's unit of work, so any refusal raises before the
caller commits and nothing is written. The caller's `expected_version` is checked once, by the
first append; each later part is chained from the version the one before it produced. All events
share one correlation id.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from tl_core.services.commands import Command, CommandResult, UpdateRecord
from tl_core.services.errors import NoChangesError
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_update_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid


class PsetEdit(BaseModel):
    """The values of one pset in one layer (see `SetPsetValues`)."""

    pset: str
    layer: Literal["standard", "custom", "project"]
    values: dict[str, Any]


class EditRecord(Command):
    stream_id: str
    expected_version: int
    changes: dict[str, Any] = {}  # as `UpdateRecord.changes`; empty: no field change
    pset_edits: list[PsetEdit] = []  # applied in order, after the field changes


def handle_edit_record(uow: UnitOfWork, cmd: EditRecord) -> CommandResult:
    """Apply the field changes, then each pset edit, as events of one correlation.

    A part that changes nothing is skipped; `NoChangesError` is raised when no part changes
    anything. Any other refusal of a part (validation, layer, voided, stale `expected_version`)
    is raised as that part's own error, and the caller's unit of work must roll back; this
    handler never commits. The result carries every event, in order, and the final version.
    """
    correlation_id = cmd.correlation_id or new_ulid()
    common: dict[str, Any] = {
        "actor": cmd.actor,
        "source": cmd.source,
        "scope": cmd.scope,
        "correlation_id": correlation_id,
        "causation_id": cmd.causation_id,
        "stream_id": cmd.stream_id,
    }
    version = cmd.expected_version
    events: list[Any] = []
    key: str | None = None
    applied = False

    def take(result: CommandResult) -> None:
        nonlocal version, key, applied
        version, key, applied = result.version, result.key, True
        events.extend(result.events)

    if cmd.changes:
        try:
            take(
                handle_update_record(
                    uow, UpdateRecord(**common, expected_version=version, changes=cmd.changes)
                )
            )
        except NoChangesError:
            pass
    for edit in cmd.pset_edits:
        try:
            take(
                handle_set_pset_values(
                    uow,
                    SetPsetValues(
                        **common,
                        expected_version=version,
                        pset=edit.pset,
                        layer=edit.layer,
                        values=edit.values,
                    ),
                )
            )
        except NoChangesError:
            pass
    if not applied:
        raise NoChangesError(f"no part of the edit of record {cmd.stream_id!r} changes anything")
    return CommandResult(stream_id=cmd.stream_id, key=key, version=version, events=events)
