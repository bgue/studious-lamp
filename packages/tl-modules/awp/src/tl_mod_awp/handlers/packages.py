"""Owner package commands: record, update and void the mirror of an engineering (EWP) or
procurement (PWP) package of the owner's system.

A reference is a project record (``awp.EWPRef`` or ``awp.PWPRef``) keyed by the owner's package
number (``awp.ewp@<no>`` / ``awp.pwp@<no>``, unique per type and project). The source of truth stays
outside: the module only mirrors the number, status words, dates and the flag that the package can
hold back field work (``constraint_source``). A reference has no workflow. Fixed messages. All the
events of a command share one correlation id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_awp.common import (
    MSG_DUPLICATE,
    append,
    correlated,
    create_coded_record,
    display_code,
    key_taken,
    load_record_of,
    require_project,
)
from tl_mod_awp.errors import DuplicateCodeError
from tl_mod_awp.names import (
    EWP,
    PACKAGE_DEFINED,
    PACKAGE_TABLE,
    PACKAGE_TYPES,
    PACKAGE_UPDATED,
    PWP,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        RecordExternalPackage,
        UpdateExternalPackage,
        VoidExternalPackage,
    )

MSG_NOTHING = "the request changes nothing"
KIND = {"ewp": EWP, "pwp": PWP}
#: The fields ``UpdateExternalPackage`` may change; a ``None`` clears all but the flag.
UPDATABLE = ("status_text", "forecast_date", "actual_date")


def _row_sql(record_type: str) -> Any:
    table = PACKAGE_TABLE[record_type]
    return text(
        f"SELECT status_text, forecast_date, actual_date, constraint_source FROM {table} "
        "WHERE id = :id"
    )


def handle_record_external_package(uow: UnitOfWork, cmd: RecordExternalPackage) -> CommandResult:
    """Record a package (``Record.Created``, ``EWPRef.Defined`` or ``PWPRef.Defined``).

    Raises ``DuplicateCodeError`` (the number is used by a package of that type in the project).
    """
    require_project(cmd)
    cmd = correlated(cmd)
    record_type = KIND[cmd.package_type]
    if key_taken(uow.conn(), cmd.scope, record_type, cmd.package_no):
        raise DuplicateCodeError(MSG_DUPLICATE)
    made = create_coded_record(
        uow,
        cmd,
        record_type=record_type,
        title=cmd.title,
        code=cmd.package_no,
        extra_events=[
            NewEvent(
                event_type=PACKAGE_DEFINED[record_type],
                payload={
                    "package_no": cmd.package_no,
                    "status_text": cmd.status_text,
                    "forecast_date": cmd.forecast_date,
                    "actual_date": cmd.actual_date,
                    "constraint_source": cmd.constraint_source,
                    "source_system": cmd.source_system,
                },
            )
        ],
    )
    return CommandResult(
        stream_id=made.stream_id, key=cmd.package_no, version=made.version, events=made.events
    )


def handle_update_external_package(uow: UnitOfWork, cmd: UpdateExternalPackage) -> CommandResult:
    """Change the status words, dates or constraint flag (``EWPRef.Updated`` or
    ``PWPRef.Updated``). Raises ``RecordNotFoundError``, ``NoChangesError``."""
    require_project(cmd)
    cmd = correlated(cmd)
    ref = load_record_of(uow, cmd.scope, cmd.id, PACKAGE_TYPES)
    row = uow.conn().execute(_row_sql(ref.record_type), {"id": ref.id}).first()
    if row is None:
        raise LookupError(f"no package row for {ref.id}")
    given = cmd.model_fields_set
    changes: dict[str, list[Any]] = {}
    for name in UPDATABLE:
        if name in given and getattr(cmd, name) != getattr(row, name):
            changes[name] = [getattr(row, name), getattr(cmd, name)]
    if cmd.constraint_source is not None and cmd.constraint_source != bool(row.constraint_source):
        changes["constraint_source"] = [bool(row.constraint_source), cmd.constraint_source]
    if not changes:
        raise NoChangesError(MSG_NOTHING)
    made = append(
        uow,
        cmd,
        ref.id,
        ref.record_type,
        [NewEvent(event_type=PACKAGE_UPDATED[ref.record_type], payload={"changes": changes})],
    )
    return CommandResult(
        stream_id=ref.id, key=display_code(ref.key), version=made.new_version, events=made.events
    )


def handle_void_external_package(uow: UnitOfWork, cmd: VoidExternalPackage) -> CommandResult:
    """Void a package reference (``Record.Voided``). Raises ``RecordNotFoundError`` (also for one
    already void)."""
    require_project(cmd)
    cmd = correlated(cmd)
    ref = load_record_of(uow, cmd.scope, cmd.id, PACKAGE_TYPES)
    made = append(
        uow,
        cmd,
        ref.id,
        ref.record_type,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=ref.id, key=display_code(ref.key), version=made.new_version, events=made.events
    )
