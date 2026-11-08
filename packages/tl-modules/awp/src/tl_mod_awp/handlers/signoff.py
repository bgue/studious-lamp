"""IWP sign-off, issue and hold (P2-I2 S3).

``SignOffIwp`` records one signer of the current record hash (``IWP.SignedOff``; no state move);
``IssueIwp`` needs two distinct signers of that hash and moves Ready to Issued; ``HoldIwp`` and
``ReleaseHold`` move to On hold and back to Constraint check. The moves are ``by_module`` workflow
transitions; the access words (``awp.iwp.signoff``, ``awp.iwp.issue``, ``awp.iwp.hold``) are the
platform's check before the handler runs. Every refusal has a fixed text: no role list, no cell.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core.auth.module_roles import effective_roles, holder_for_actor
from tl_core.ledger import NewEvent, canonical_json
from tl_core.services.commands import CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_awp.common import append, correlated, has_table, move, require_project, setting_value
from tl_mod_awp.errors import IwpNotReadyError, IwpRuleError, IwpSignoffError
from tl_mod_awp.facts import iwp_facts
from tl_mod_awp.handlers.iwp import Iwp, check_foreman, load_iwp, require_state
from tl_mod_awp.names import (
    IWP,
    IWP_HELD,
    IWP_HOLD_RELEASED,
    IWP_ISSUED_EVENT,
    IWP_SIGNED_OFF,
    IWP_TABLE,
    READINESS_CHECK_TABLE,
    READINESS_TABLE,
    SIGNERS_NEEDED,
    SIGNOFF_ROLES_SETTING,
    UNKNOWN_CHECKS_SETTING,
)
from tl_mod_awp.projectors.iwp import signoff_rows

if TYPE_CHECKING:
    from tl_mod_awp.commands import HoldIwp, IssueIwp, ReleaseHold, SignOffIwp

MSG_NO_ROLE = "the signer does not hold a role that may sign off a package"
MSG_REPEAT = "the signer already signed this version of the package"
MSG_STALE = "the package changed since the hash was read"
MSG_NOT_READY = "the package is not ready"
MSG_TWO = "two distinct signers must sign off the current version first"
MSG_NO_FOREMAN = "a foreman is required"

_PINS_SQL = text(
    "SELECT link_id, pin FROM cur_links WHERE from_id = :id AND status = 'active' "
    "AND pin IS NOT NULL ORDER BY link_id"
)
_HASHED = (
    "discipline",
    "cwp_id",
    "planned_start",
    "planned_finish",
    "foreman",
    "estimated_hours",
    "crew_text",
)
_FIELDS_SQL = text(f"SELECT {', '.join(_HASHED)} FROM {IWP_TABLE} WHERE id = :id")
_SIGNOFFS_SQL = text(f"SELECT signoffs_json FROM {IWP_TABLE} WHERE id = :id")
_READY_SQL = text(f"SELECT ready FROM {READINESS_TABLE} WHERE iwp_id = :id")
_UNKNOWN_SQL = text(
    f"SELECT 1 FROM {READINESS_CHECK_TABLE} WHERE iwp_id = :id AND state = 'unknown' LIMIT 1"
)


def iwp_record_hash(conn: Connection, iwp_id: str) -> str:
    """SHA-256 (hex) of the IWP as signed: discipline, work package, planned dates, foreman,
    estimated hours, crew text, the sorted scope ids and the sorted pinned document links with
    their pin codes."""
    row = conn.execute(_FIELDS_SQL, {"id": iwp_id}).mappings().one()
    pins = [
        {"link_id": str(r[0]), "pin": str(r[1])} for r in conn.execute(_PINS_SQL, {"id": iwp_id})
    ]
    scope_ids = iwp_facts(conn, iwp_id).scope_ids
    body = {
        **{name: row[name] for name in _HASHED},
        "scope_ids": sorted(i for ids in scope_ids.values() for i in ids),
        "pins": pins,
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _require_hash(uow: UnitOfWork, iwp: Iwp, given: str) -> str:
    current = iwp_record_hash(uow.conn(), iwp.id)
    if given != current:
        raise IwpSignoffError(MSG_STALE)
    return current


def _require_ready(conn: Connection, scope: str, iwp_id: str) -> None:
    """The last readiness result says ready (absent is not ready); an unknown check refuses unless
    ``awp.release.allow_unknown_checks``."""
    if not has_table(conn, READINESS_TABLE):
        raise IwpNotReadyError(MSG_NOT_READY)
    ready = conn.execute(_READY_SQL, {"id": iwp_id}).scalar_one_or_none()
    if ready is None or not bool(ready):
        raise IwpNotReadyError(MSG_NOT_READY)
    if not setting_value(conn, scope, UNKNOWN_CHECKS_SETTING):
        if conn.execute(_UNKNOWN_SQL, {"id": iwp_id}).first() is not None:
            raise IwpNotReadyError(MSG_NOT_READY)


def _signers(conn: Connection, iwp_id: str, record_hash: str) -> list[str]:
    held = conn.execute(_SIGNOFFS_SQL, {"id": iwp_id}).scalar_one_or_none()
    return [str(r["by"]) for r in signoff_rows(held) if r["record_hash"] == record_hash]


def _signing_role(conn: Connection, actor: str, scope: str) -> str:
    """The first role of ``awp.release.signoff_roles`` the actor holds in the project (an admin
    holds them all); refused with a fixed message otherwise."""
    wanted = [str(r) for r in setting_value(conn, scope, SIGNOFF_ROLES_SETTING)]
    held = effective_roles(conn, holder_for_actor(conn, actor), scope=scope, module="awp").roles
    for role in wanted:
        if role in held:
            return role
    raise IwpSignoffError(MSG_NO_ROLE)


def handle_sign_off_iwp(uow: UnitOfWork, cmd: SignOffIwp) -> CommandResult:
    """Record one signer of the current hash. Raises ``IwpStateError`` (not Ready),
    ``IwpSignoffError`` (role, stale hash, a repeat), ``IwpNotReadyError``."""
    require_project(cmd)
    cmd = correlated(cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, "SignOffIwp")
    conn = uow.conn()
    role = _signing_role(conn, cmd.actor, cmd.scope)
    current = _require_hash(uow, iwp, cmd.record_hash)
    _require_ready(conn, cmd.scope, iwp.id)
    if cmd.actor in _signers(conn, iwp.id, current):
        raise IwpSignoffError(MSG_REPEAT)
    done = append(
        uow,
        cmd,
        iwp.id,
        IWP,
        [
            NewEvent(
                event_type=IWP_SIGNED_OFF,
                payload={"by": cmd.actor, "role": role, "record_hash": current},
            )
        ],
    )
    return CommandResult(
        stream_id=iwp.id, key=iwp.key, version=done.new_version, events=done.events
    )


def handle_issue_iwp(uow: UnitOfWork, cmd: IssueIwp) -> CommandResult:
    """Issue to the foreman: ``IWP.Issued`` then the move ``issue``. Raises ``IwpStateError``,
    ``IwpNotReadyError``, ``IwpSignoffError`` (stale hash, fewer than two signers),
    ``IwpRuleError`` (no foreman, not an account). A missing permit is reported by the workflow."""
    require_project(cmd)
    cmd = correlated(cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, "IssueIwp")
    conn = uow.conn()
    current = _require_hash(uow, iwp, cmd.record_hash)
    _require_ready(conn, cmd.scope, iwp.id)
    if len(set(_signers(conn, iwp.id, current))) < SIGNERS_NEEDED:
        raise IwpSignoffError(MSG_TWO)
    foreman = cmd.foreman or iwp.foreman
    if foreman is None:
        raise IwpRuleError(MSG_NO_FOREMAN)
    check_foreman(conn, foreman)
    issued = append(
        uow,
        cmd,
        iwp.id,
        IWP,
        [NewEvent(event_type=IWP_ISSUED_EVENT, payload={"by": cmd.actor, "foreman": foreman})],
    )
    moved = move(uow, cmd, iwp.id, "issue")
    return CommandResult(
        stream_id=iwp.id,
        key=iwp.key,
        version=moved.version,
        events=[*issued.events, *moved.events],
    )


def _held(
    uow: UnitOfWork,
    cmd: Any,
    command: str,
    event: str,
    payload: dict[str, Any],
    transition: str,
    reason: str | None,
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, command)
    done = append(uow, cmd, iwp.id, IWP, [NewEvent(event_type=event, payload=payload)])
    moved = move(uow, cmd, iwp.id, transition, reason)
    return CommandResult(
        stream_id=iwp.id, key=iwp.key, version=moved.version, events=[*done.events, *moved.events]
    )


def handle_hold_iwp(uow: UnitOfWork, cmd: HoldIwp) -> CommandResult:
    """Ready, Issued or In progress to On hold: ``IWP.Held`` then the move ``hold``."""
    return _held(
        uow, cmd, "HoldIwp", IWP_HELD, {"by": cmd.actor, "reason": cmd.reason}, "hold", cmd.reason
    )


def handle_release_hold(uow: UnitOfWork, cmd: ReleaseHold) -> CommandResult:
    """On hold to Constraint check (no memory of the prior state): ``IWP.HoldReleased``."""
    return _held(uow, cmd, "ReleaseHold", IWP_HOLD_RELEASED, {}, "release_hold", cmd.reason)


__all__ = [
    "handle_hold_iwp",
    "handle_issue_iwp",
    "handle_release_hold",
    "handle_sign_off_iwp",
    "iwp_record_hash",
]
