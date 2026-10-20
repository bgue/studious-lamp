"""Waivers: request, approve, revoke (brief 6.3, 27.5).

A waiver relaxes one property of one project's effective schema until a date. Anyone signed in
may ask; an administrator approves or revokes, and never the person who asked. An approved waiver
reaches the conformance evaluator through the registry source (``tl_mod_schemareg.source``) as
part of the project's effective schema, so approving or revoking one changes the schema's hash.

A project whose own package declares the conformance mode ``strict`` or ``lenient`` cannot honour
waivers (the evaluator drops waivers only in ``strict_with_waivers``); a request for such a project
is refused instead of approved to no effect.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from pydantic import ConfigDict, Field
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text
from tl_core.uow import UnitOfWork
from tl_schema.effective import resolve_path

from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.common import append, bump, correlated, scoped, today_in, transition
from tl_mod_schemareg.errors import (
    InvalidWaiverError,
    SelfReviewError,
    WaiverNotFoundError,
    WaiverStateError,
)
from tl_mod_schemareg.limits import (
    MAX_COMMENT,
    MAX_OPEN_WAIVERS,
    MAX_PATH,
    MAX_PROJECT,
    MAX_REASON,
    WAIVER_MAX_DAYS,
)
from tl_mod_schemareg.names import (
    REQUESTED,
    WAIVER,
    WAIVER_APPROVED,
    WAIVER_APPROVED_STATE,
    WAIVER_REQUESTED,
    WAIVER_REVOKED,
)

_PROJECT = re.compile(r"[A-Za-z0-9_.-]+")
_PATH = re.compile(r"psets\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*|\.x\.[a-z][a-z0-9_]*)")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class RequestWaiver(Command):
    """Ask to relax ``path`` for ``project`` until ``expires``. The command's scope is ignored."""

    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1, max_length=MAX_PROJECT)
    path: str = Field(min_length=1, max_length=MAX_PATH)
    reason: str = Field(min_length=1, max_length=MAX_REASON)
    expires: str = Field(min_length=10, max_length=10)  # YYYY-MM-DD


class ApproveWaiver(Command):
    model_config = ConfigDict(extra="forbid")

    waiver_id: str
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)


class RevokeWaiver(Command):
    """Revoke an approved waiver, or refuse a requested one."""

    model_config = ConfigDict(extra="forbid")

    waiver_id: str
    reason: str = Field(min_length=1, max_length=MAX_REASON)


def _load(uow: UnitOfWork, waiver_id: str) -> registry.WaiverRow:
    row = registry.get_waiver(uow.conn(), waiver_id)
    if row is None:
        raise WaiverNotFoundError(f"no waiver {waiver_id!r}")
    return row


def _expiry(text: str) -> date:
    if _DATE.fullmatch(text) is None or not text.isascii():
        raise InvalidWaiverError("expires must be written YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise InvalidWaiverError("expires is not a real date") from exc


def _declared_mode_blocks(scope: str) -> str | None:
    """The mode a package of the project declares when it cannot honour waivers, else ``None``."""
    held = analysis.provider()
    for doc in held.registry().adopted(scope, held.pins_of(scope)):
        if doc.conformance is not None and doc.conformance.mode != "strict_with_waivers":
            return f"{doc.key()} declares the conformance mode {doc.conformance.mode}"
    return None


def handle_request_waiver(uow: UnitOfWork, cmd: RequestWaiver) -> CommandResult:
    """Record the request. Raises ``InvalidWaiverError``."""
    cmd = correlated(cmd)
    if _PROJECT.fullmatch(cmd.project) is None:
        raise InvalidWaiverError("the project is not written in a form that can be used")
    if _PATH.fullmatch(cmd.path) is None:
        raise InvalidWaiverError(
            "path must look like psets.<pset>.<property> or psets.<pset>.x.<property>"
        )
    scope = f"project:{cmd.project}"
    cmd = scoped(cmd, scope)
    until = _expiry(cmd.expires)
    now = today_in(scope)
    if until < now:
        raise InvalidWaiverError("expires is in the past")
    if until > now + timedelta(days=WAIVER_MAX_DAYS):
        raise InvalidWaiverError(f"a waiver holds for {WAIVER_MAX_DAYS} days at most")
    schema = analysis.provider().effective(scope)
    if resolve_path(schema, cmd.path) is None:
        raise InvalidWaiverError(f"{cmd.path} names no property of {scope}")
    blocked = _declared_mode_blocks(scope)
    if blocked is not None:
        raise InvalidWaiverError(f"{blocked}; waivers have no effect there")
    conn = uow.conn()
    same = registry.list_waivers(conn, project=cmd.project, path=cmd.path)
    live = [
        w
        for w in same
        if w.state == REQUESTED or (w.state == WAIVER_APPROVED_STATE and _expiry(w.expires) >= now)
    ]
    if live:
        raise InvalidWaiverError(f"{cmd.path} is already waived or asked for ({live[0].key})")
    open_count = sum(
        1
        for w in registry.list_waivers(conn, project=cmd.project)
        if w.state == REQUESTED or (w.state == WAIVER_APPROVED_STATE and _expiry(w.expires) >= now)
    )
    if open_count >= MAX_OPEN_WAIVERS:
        raise InvalidWaiverError(f"{cmd.project} has {MAX_OPEN_WAIVERS} open waivers already")
    number = max((w.number for w in same), default=0) + 1
    return create_module_record(
        uow,
        cmd,
        record_type=WAIVER,
        title=f"Waiver {cmd.path}",
        key=f"{cmd.project}/{cmd.path}@{number}",
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=WAIVER_REQUESTED,
                payload={
                    "project": cmd.project,
                    "path": cmd.path,
                    "number": number,
                    "reason": cmd.reason,
                    "expires": cmd.expires,
                    "requested_by": cmd.actor,
                },
            )
        ],
    )


def handle_approve_waiver(uow: UnitOfWork, cmd: ApproveWaiver) -> CommandResult:
    """Approve a requested waiver. The person who asked cannot."""
    cmd = correlated(cmd)
    row = _load(uow, cmd.waiver_id)
    if row.state != REQUESTED:
        raise WaiverStateError(f"{row.key} is {row.state}; only a requested waiver is approved")
    if cmd.actor == row.requested_by:
        raise SelfReviewError(f"{cmd.actor} asked for {row.key} and cannot approve it")
    if _expiry(row.expires) < today_in(row.scope):
        raise WaiverStateError(f"{row.key} expired on {row.expires}; ask again")
    blocked = _declared_mode_blocks(row.scope)
    if blocked is not None:
        raise InvalidWaiverError(f"{blocked}; waivers have no effect there")
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "approve")
    done = append(
        uow,
        cmd,
        row.id,
        WAIVER,
        [
            NewEvent(
                event_type=WAIVER_APPROVED,
                payload={"approver": cmd.actor, "comment": clean_optional_text(cmd.comment)},
            )
        ],
    )
    bump()
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


def handle_revoke_waiver(uow: UnitOfWork, cmd: RevokeWaiver) -> CommandResult:
    """Revoke an approved waiver or refuse a requested one."""
    cmd = correlated(cmd)
    row = _load(uow, cmd.waiver_id)
    if row.state not in (REQUESTED, WAIVER_APPROVED_STATE):
        raise WaiverStateError(f"{row.key} is {row.state}; there is nothing to revoke")
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "revoke", reason=cmd.reason)
    done = append(
        uow,
        cmd,
        row.id,
        WAIVER,
        [
            NewEvent(
                event_type=WAIVER_REVOKED,
                payload={"revoked_by": cmd.actor, "reason": cmd.reason},
            )
        ],
    )
    bump()
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )
