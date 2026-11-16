"""The scan code service: the one path every issue, rotate and revoke takes (P2-QR S2).

``issue`` and ``rotate`` return an ``IssuedCode``: the secret code leaves here once, to the
caller that prints it (the CLI, the web form). The command handlers in ``module.COMMANDS`` call
the same functions and drop the code, so there is one code path and the handler is the service
minus the return. The code is never stored, logged, put in an event, an error text or a repr
(``IssuedCode.code`` is excluded from its repr); the events hold the hash only.

Every id a command is given is checked first: a record or code the actor may not read (a code is
hidden when its target is), an absent id, another project, a voided one and a target type that no
scan-card provider serves all give the one ``MSG_UNKNOWN``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.ledger import NewEvent
from tl_core.qr import registry
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_qr.codes import code_hash, new_code
from tl_mod_qr.commands import IssueScanCode, RevokeScanCode, RotateScanCode
from tl_mod_qr.errors import (
    MSG_BASE,
    MSG_CAP,
    MSG_EXPIRY,
    MSG_REVOKED,
    MSG_UNKNOWN,
    QrRuleError,
    QrStateError,
)
from tl_mod_qr.names import (
    FEED_NONE,
    SCAN_CODE,
    SCAN_CODE_ISSUED,
    SCAN_CODE_REVOKED,
    SCAN_CODE_TABLE,
)

BASE_URL = "api.public_base_url"
CAP = "qr.codes_per_record_max"
TITLE = "Scan code"

_ENVELOPE = text("SELECT id, scope, type, voided, version FROM cur_core_record WHERE id = :id")
_CODE_ROW = text(f"SELECT * FROM {SCAN_CODE_TABLE} WHERE id = :id")
_LIVE = text(
    f"SELECT id, expires_on FROM {SCAN_CODE_TABLE} WHERE target_id = :t AND revoked_at IS NULL"
)


@dataclass(frozen=True)
class IssuedCode:
    """The result of ``issue`` or ``rotate``: the code (shown once, never in a repr) and the
    command result of the new scan code's record."""

    code: str = field(repr=False)
    result: CommandResult


@dataclass(frozen=True)
class _Fields:
    target_id: str
    label_text: str | None
    size: str
    expires_on: date | None


def _correlated[C: Command](cmd: C) -> C:
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def _day(value: Any) -> str | None:
    return None if value is None else str(value)[:10]


def _unknown() -> RecordNotFoundError:
    return RecordNotFoundError(MSG_UNKNOWN)


def _visible_record(uow: UnitOfWork, scope: str, record_id: str) -> Any:
    """The envelope row of a record the actor may read in ``scope``; one text otherwise."""
    conn = uow.conn()
    try:
        confidentiality.require_visible(conn, record_id)
    except RecordNotFoundError:
        raise _unknown() from None
    env = conn.execute(_ENVELOPE, {"id": record_id}).first()
    if env is None or env.scope != scope or bool(env.voided):
        raise _unknown()
    return env


def _providers() -> set[str]:
    try:
        return set(registry.load_scan_cards())
    except registry.ScanCardLoadError:
        return set()


def _append(
    uow: UnitOfWork, cmd: Command, stream_id: str, version: int, events: list[NewEvent]
) -> Any:
    return uow.append(
        stream_id=stream_id,
        stream_type=SCAN_CODE,
        scope=cmd.scope,
        expected_version=version,
        events=events,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def _issue(
    uow: UnitOfWork, cmd: Command, fields: _Fields, replacing: tuple[str, int, str] | None
) -> IssuedCode:
    """Issue a code for ``fields``; when ``replacing`` (old id, its version, reason) is given,
    revoke that code first in the same unit of work, with ``replaced_by_id`` set."""
    conn = uow.conn()
    if not str(value_of(conn, BASE_URL, project=project_of_scope(cmd.scope)) or ""):
        raise QrRuleError(MSG_BASE)
    target = _visible_record(uow, cmd.scope, fields.target_id)
    if str(target.type) not in _providers():
        raise _unknown()
    today = utcnow().date().isoformat()
    if fields.expires_on is not None and fields.expires_on.isoformat() < today:
        raise QrRuleError(MSG_EXPIRY)
    cap = int(value_of(conn, CAP, project=project_of_scope(cmd.scope)))
    skip = replacing[0] if replacing else None
    live = [
        r
        for r in conn.execute(_LIVE, {"t": target.id}).all()
        if r.id != skip and (_day(r.expires_on) is None or str(_day(r.expires_on)) >= today)
    ]
    if len(live) >= cap:
        raise QrRuleError(MSG_CAP)
    new_id = new_ulid()
    code = new_code()
    revoked: list[Any] = []
    if replacing is not None:
        old_id, old_version, reason = replacing
        revoked = _append(
            uow,
            cmd,
            old_id,
            old_version,
            [
                NewEvent(
                    event_type=SCAN_CODE_REVOKED,
                    payload={
                        "record_id": old_id,
                        "reason": reason,
                        "replaced_by_id": new_id,
                        "feed_policy": FEED_NONE,
                    },
                )
            ],
        ).events
    made = uow.append(
        stream_id=new_id,
        stream_type=SCAN_CODE,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": SCAN_CODE,
                    "key": None,
                    "title": TITLE,
                    "description": None,
                    "psets": {},
                },
            ),
            NewEvent(
                event_type=SCAN_CODE_ISSUED,
                payload={
                    "record_id": new_id,
                    "code_hash": code_hash(code),
                    "target_id": str(target.id),
                    "target_type": str(target.type),
                    "label_text": fields.label_text,
                    "size": fields.size,
                    "expires_on": None
                    if fields.expires_on is None
                    else fields.expires_on.isoformat(),
                    "feed_policy": FEED_NONE,
                },
            ),
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    result = CommandResult(
        stream_id=new_id, key=None, version=made.new_version, events=[*revoked, *made.events]
    )
    return IssuedCode(code=code, result=result)


def _load_code(uow: UnitOfWork, cmd: Command, code_id: str) -> tuple[Any, Any]:
    """The code's envelope and typed row; one text for a hidden, absent, foreign or voided one."""
    env = _visible_record(uow, cmd.scope, code_id)
    row = uow.conn().execute(_CODE_ROW, {"id": code_id}).mappings().first()
    if env.type != SCAN_CODE or row is None:
        raise _unknown()
    return env, row


def issue(uow: UnitOfWork, cmd: IssueScanCode) -> IssuedCode:
    """Issue a code: the setting, a readable target with a card provider, an expiry not past, the
    cap. Appends ``Record.Created`` and ``ScanCode.Issued`` (the hash only); never commits."""
    cmd = _correlated(cmd)
    return _issue(uow, cmd, _Fields(cmd.target_id, cmd.label_text, cmd.size, cmd.expires_on), None)


def revoke(uow: UnitOfWork, cmd: RevokeScanCode) -> CommandResult:
    """Revoke a live code; ``QrStateError`` (fixed text) when it already is."""
    cmd = _correlated(cmd)
    env, row = _load_code(uow, cmd, cmd.code_id)
    if row["revoked_at"] is not None:
        raise QrStateError(MSG_REVOKED)
    done = _append(
        uow,
        cmd,
        cmd.code_id,
        int(env.version),
        [
            NewEvent(
                event_type=SCAN_CODE_REVOKED,
                payload={
                    "record_id": cmd.code_id,
                    "reason": cmd.reason,
                    "replaced_by_id": None,
                    "feed_policy": FEED_NONE,
                },
            )
        ],
    )
    return CommandResult(
        stream_id=cmd.code_id, key=None, version=done.new_version, events=done.events
    )


def rotate(uow: UnitOfWork, cmd: RotateScanCode) -> IssuedCode:
    """Revoke the old code (``replaced_by_id`` set) and issue a new one for the same target,
    label, size and expiry, in one unit of work. The actor needs the target's read right, not the
    revoke word."""
    cmd = _correlated(cmd)
    env, row = _load_code(uow, cmd, cmd.code_id)
    if row["revoked_at"] is not None:
        raise QrStateError(MSG_REVOKED)
    expires = _day(row["expires_on"])
    fields = _Fields(
        target_id=str(row["target_id"]),
        label_text=row["label_text"],
        size=str(row["size"]),
        expires_on=None if expires is None else date.fromisoformat(expires),
    )
    return _issue(uow, cmd, fields, (cmd.code_id, int(env.version), cmd.reason))
