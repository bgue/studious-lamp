"""Location tree commands: ``DefineLocation``, ``ReviseLocation`` and ``RetireLocation``.

The tree rules (decision 5 of the S2 spec): one root per project (kind ``project``, no parent), a
second root is refused; a new location needs an active parent in the same project and sits one level
below it, at most ``MAX_DEPTH`` (5) below the root; ``ReviseLocation`` changes title and kind
only (no
re-parenting); ``RetireLocation`` is refused while any stock row at the location is not zero or an
active child exists. Locations are found by ``code`` in the command's project scope.

``check_define_location`` is the rule of ``DefineLocation``, run by the handler and by the load
target's plan (``planned`` holds the depth of the locations an earlier row of the same file would
make, so a file may list parents first).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import Connection
from tl_core.confidentiality import require_visible
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import DuplicateKeyError
from tl_core.services.records import create_module_record
from tl_core.text import clean_text
from tl_core.uow import UnitOfWork

from tl_mod_materials.common import append, check_one_of, correlated, require_project
from tl_mod_materials.errors import (
    LocationNotFoundError,
    LocationTreeError,
    NoChangesError,
)
from tl_mod_materials.limits import (
    LOCATION_CODE,
    LOCATION_KINDS,
    MAX_DEPTH,
    MAX_LOCATION_CODE,
    MAX_REASON,
    MAX_TITLE,
)
from tl_mod_materials.names import (
    LOCATION,
    LOCATION_DEFINED,
    LOCATION_RETIRED,
    LOCATION_REVISED,
)
from tl_mod_materials.registry import (
    LocationRow,
    get_location,
    has_active_child,
    has_root,
    holds_stock,
    record_type_of_key,
)

ROOT_KIND = "project"


def _code(value: str) -> str:
    if LOCATION_CODE.fullmatch(value) is None:
        raise ValueError("code must be upper-case letters, digits, '.' or '-', at most 16")
    return value


def _title(value: str) -> str:
    if not value.strip():
        raise ValueError("title must not be blank")
    return clean_text(value)


class DefineLocation(Command):
    """Define a location in the project's tree (the root has no ``parent_code``)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_LOCATION_CODE)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    kind: str = Field(min_length=1, max_length=16)
    parent_code: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION_CODE)

    @field_validator("code", "parent_code")
    @classmethod
    def _check_code(cls, value: str | None) -> str | None:
        return None if value is None else _code(value)

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        return _title(value)


class ReviseLocation(Command):
    """Rename a location or change its kind (a location is never re-parented)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_LOCATION_CODE)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    kind: str | None = Field(default=None, min_length=1, max_length=16)

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return _code(value)

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str | None) -> str | None:
        return None if value is None else _title(value)


class RetireLocation(Command):
    """Retire a location; refused while stock is held there or an active child exists."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_LOCATION_CODE)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return _code(value)

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return clean_text(value)


# --- the rules -----------------------------------------------------------------------------------


def check_define_location(
    conn: Connection, cmd: DefineLocation, *, planned: Mapping[str, int] | None = None
) -> tuple[str | None, int]:
    """``(parent id, depth)`` of the new location, or a refusal.

    ``planned`` maps the codes an earlier row of the same file would create to their depth (the
    load target's plan); the parent's id is then ``None`` and the apply stage resolves it.
    """
    check_one_of(cmd.kind, LOCATION_KINDS, "kind")
    if record_type_of_key(conn, cmd.scope, cmd.code) is not None or (
        planned is not None and cmd.code in planned
    ):
        raise DuplicateKeyError("the location code is already used in the project")
    if cmd.parent_code is None:
        if cmd.kind != ROOT_KIND:
            raise LocationTreeError(
                f"a location with no parent is the root; its kind is {ROOT_KIND}"
            )
        if has_root(conn, cmd.scope) or (planned is not None and 0 in planned.values()):
            raise LocationTreeError("the project already has its root location")
        return None, 0
    if cmd.kind == ROOT_KIND:
        raise LocationTreeError(f"only the root has the kind {ROOT_KIND}")
    if planned is not None and cmd.parent_code in planned:
        parent_id, parent_depth = None, planned[cmd.parent_code]
    else:
        parent = get_location(conn, cmd.scope, cmd.parent_code)
        if parent is None:
            raise LocationNotFoundError("the parent location does not exist in the project")
        if parent.retired:
            raise LocationTreeError("the parent location is retired")
        require_visible(conn, parent.id)
        parent_id, parent_depth = parent.id, parent.depth
    depth = parent_depth + 1
    if depth > MAX_DEPTH:
        raise LocationTreeError(f"the location tree is at most {MAX_DEPTH} levels below the root")
    return parent_id, depth


def handle_define_location(uow: UnitOfWork, cmd: DefineLocation) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    parent_id, depth = check_define_location(uow.conn(), cmd)
    return create_module_record(
        uow,
        cmd,
        record_type=LOCATION,
        title=cmd.title,
        key=cmd.code,
        extra_events=[
            NewEvent(
                event_type=LOCATION_DEFINED,
                payload={
                    "code": cmd.code,
                    "kind": cmd.kind,
                    "parent_id": parent_id,
                    "depth": depth,
                },
            )
        ],
    )


def _live_location(conn: Connection, scope: str, code: str) -> LocationRow:
    row = get_location(conn, scope, code)
    if row is None:
        raise LocationNotFoundError(f"no location {code!r} in {scope}")
    require_visible(conn, row.id)
    return row


def handle_revise_location(uow: UnitOfWork, cmd: ReviseLocation) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    row = _live_location(conn, cmd.scope, cmd.code)
    if row.retired:
        raise LocationTreeError(f"location {cmd.code!r} is retired")
    payload: dict[str, str] = {}
    events: list[NewEvent] = []
    if cmd.title is not None and cmd.title != row.title:
        payload["title"] = cmd.title
        events.append(
            NewEvent(
                event_type="Record.Updated",
                payload={"changes": {"title": [row.title, cmd.title]}},
            )
        )
    if cmd.kind is not None and cmd.kind != row.kind:
        check_one_of(cmd.kind, LOCATION_KINDS, "kind")
        if (cmd.kind == ROOT_KIND) != (row.parent_id is None):
            raise LocationTreeError(f"only the root has the kind {ROOT_KIND}")
        payload["kind"] = cmd.kind
    if not payload:
        raise NoChangesError(f"the revision changes nothing in location {cmd.code!r}")
    events.append(NewEvent(event_type=LOCATION_REVISED, payload=payload))
    result = append(uow, cmd, row.id, LOCATION, events)
    return CommandResult(
        stream_id=row.id, key=row.code, version=result.new_version, events=result.events
    )


def check_retire_location(conn: Connection, row: LocationRow) -> None:
    """Refuse the retirement of a location that holds stock or has an active child."""
    if row.retired:
        raise LocationTreeError(f"location {row.code!r} is already retired")
    if holds_stock(conn, row.id):
        raise LocationTreeError(f"location {row.code!r} still holds stock")
    if has_active_child(conn, row.id):
        raise LocationTreeError(f"location {row.code!r} still has an active child location")


def handle_retire_location(uow: UnitOfWork, cmd: RetireLocation) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    row = _live_location(conn, cmd.scope, cmd.code)
    check_retire_location(conn, row)
    result = append(
        uow,
        cmd,
        row.id,
        LOCATION,
        [NewEvent(event_type=LOCATION_RETIRED, payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=row.id, key=row.code, version=result.new_version, events=result.events
    )
