"""Intake commands: issue and revoke a code, accept and reject a received item (P2-FORMS S7c).

Decisions D15 to D18 (``docs/tickets/P2-FORMS/S7c-intake-commands.md``):

* The server never sees a code: ``IssueIntakeCode`` takes its hash (D16).
* Accept runs the controller's completed command through the nested seam
  (``tl_core.services.nested``), as the controller and with their holder, so they need their own
  word for it; the staged body is read once, for the sender's claim (name and company, never the
  phone), and never becomes the command (D17).
* Accept deletes the body row and appends ``IntakeItem.Purged`` in the same unit of work (D18);
  this handler and S6's purge are the only code that deletes ``forms_intake_body`` rows.

Every id a command is given is checked first: an item or code the actor may not read (through its
code's context), an absent id, another type and another project give the one ``MSG_UNKNOWN``,
before any state or argument. No text here carries a body, a claim, a code, a hash or a command
argument.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.nested import run_nested_command
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.text import FORBIDDEN_TEXT
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_forms.errors import (
    MSG_CODE_TAKEN,
    MSG_EXPIRY,
    MSG_NOT_ACCEPTED_AS,
    MSG_NOT_INTAKE,
    MSG_NOT_PUBLISHED,
    MSG_UNKNOWN,
    FormRuleError,
    FormStateError,
)
from tl_mod_forms.handlers.common import (
    append,
    correlated,
    load_template,
    move,
    record_state,
    require_project,
    require_subject,
    require_version,
    silent,
)
from tl_mod_forms.names import (
    ACTIVE,
    INTAKE_BODY_TABLE,
    INTAKE_CODE,
    INTAKE_CODE_ISSUED,
    INTAKE_CODE_MAX_DAYS,
    INTAKE_CODE_REVOKED,
    INTAKE_CODE_TABLE,
    INTAKE_ITEM,
    INTAKE_ITEM_ACCEPTED,
    INTAKE_ITEM_PURGED,
    INTAKE_ITEM_REJECTED,
    INTAKE_ITEM_TABLE,
    PENDING,
    PUBLISHED,
    T_ACCEPT,
    T_REJECT,
    T_REVOKE,
)

if TYPE_CHECKING:
    from tl_mod_forms.commands import (
        AcceptIntakeItem,
        IssueIntakeCode,
        RejectIntakeItem,
        RevokeIntakeCode,
    )

MAX_CLAIM = 80
_ENVELOPE_SQL = text("SELECT id, scope, type, voided FROM cur_core_record WHERE id = :id")
_CODE_SQL = text(f"SELECT * FROM {INTAKE_CODE_TABLE} WHERE id = :id")
_ITEM_SQL = text(f"SELECT * FROM {INTAKE_ITEM_TABLE} WHERE id = :id")
_HASH_SQL = text(f"SELECT 1 FROM {INTAKE_CODE_TABLE} WHERE code_hash = :h")
_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")
_RECEIVED_SQL = text(
    "SELECT event_id FROM events WHERE stream_id = :id AND event_type = 'IntakeItem.Received' "
    "ORDER BY seq LIMIT 1"
)
_BODY_SQL = text(f"SELECT body FROM {INTAKE_BODY_TABLE} WHERE item_id = :id")
_DELETE_BODY_SQL = text(f"DELETE FROM {INTAKE_BODY_TABLE} WHERE item_id = :id")


@dataclass(frozen=True)
class _Row:
    id: str
    state: str
    row: dict[str, Any]


def _load(uow: UnitOfWork, cmd: Command, record_id: str, record_type: str, initial: str) -> _Row:
    """The code or item in ``cmd.scope`` the actor may read; ``MSG_UNKNOWN`` for any other."""
    conn = uow.conn()
    try:
        confidentiality.require_visible(conn, record_id)
    except RecordNotFoundError:
        raise RecordNotFoundError(MSG_UNKNOWN) from None
    env = conn.execute(_ENVELOPE_SQL, {"id": record_id}).first()
    table_sql = _CODE_SQL if record_type == INTAKE_CODE else _ITEM_SQL
    row = conn.execute(table_sql, {"id": record_id}).mappings().first()
    if (
        env is None
        or row is None
        or env.type != record_type
        or env.scope != cmd.scope
        or bool(env.voided)
    ):
        raise RecordNotFoundError(MSG_UNKNOWN)
    return _Row(id=record_id, state=record_state(uow, record_id, initial), row=dict(row))


def _require_state(found: _Row, command: str, state: str) -> None:
    if found.state != state:
        raise FormStateError(f"a record that is {found.state} does not take {command}")


def _create(
    uow: UnitOfWork, cmd: Command, record_type: str, title: str, events: list[NewEvent]
) -> CommandResult:
    """``Record.Created`` with no key (intake codes take no number, so there is no pattern for
    ``create_module_record`` to allocate from) and the module's events, in one append."""
    stream_id = new_ulid()
    made = uow.append(
        stream_id=stream_id,
        stream_type=record_type,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": record_type,
                    "key": None,
                    "title": title,
                    "description": None,
                    "psets": {},
                },
            ),
            *events,
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=stream_id, key=None, version=made.new_version, events=made.events
    )


# --- codes -------------------------------------------------------------------------------------


def handle_issue_intake_code(uow: UnitOfWork, cmd: IssueIntakeCode) -> CommandResult:
    """Issue a code: project scope, a readable context in that project, a Published public intake
    template (version and hash pinned), an expiry within the setting, a hash not used before."""
    require_project(cmd)
    cmd = correlated(cmd)
    require_subject(uow, cmd, cmd.context_id)
    conn = uow.conn()
    template = load_template(uow, cmd.template_id)
    if template.state != PUBLISHED:
        raise FormRuleError(MSG_NOT_PUBLISHED)
    if template.intake != "public" or template.bound_record_type is not None:
        raise FormRuleError(MSG_NOT_INTAKE)
    longest = int(value_of(conn, INTAKE_CODE_MAX_DAYS, project=project_of_scope(cmd.scope)))
    first = utcnow().date()
    if not first <= cmd.expires_on <= first + timedelta(days=longest):
        raise FormRuleError(MSG_EXPIRY)
    if conn.execute(_HASH_SQL, {"h": cmd.code_hash}).first() is not None:
        raise FormRuleError(MSG_CODE_TAKEN)
    context_type: str | None = None
    if cmd.context_id is not None:
        found = conn.execute(_TYPE_SQL, {"id": cmd.context_id}).scalar_one_or_none()
        context_type = None if found is None else str(found)
    issued = NewEvent(
        event_type=INTAKE_CODE_ISSUED,
        payload=silent(
            {
                "code_hash": cmd.code_hash,
                "template_id": template.id,
                "template_version": template.version,
                "template_hash": template.content_hash,
                "context_id": cmd.context_id,
                "context_type": context_type,
                "heading": cmd.heading,
                "controller_role": cmd.controller_role,
                "expires_on": cmd.expires_on.isoformat(),
            }
        ),
    )
    return _create(uow, cmd, INTAKE_CODE, cmd.heading, [issued])


def handle_revoke_intake_code(uow: UnitOfWork, cmd: RevokeIntakeCode) -> CommandResult:
    """Active to Revoked."""
    require_project(cmd)
    cmd = correlated(cmd)
    code = _load(uow, cmd, cmd.code_id, INTAKE_CODE, ACTIVE)
    _require_state(code, "RevokeIntakeCode", ACTIVE)
    require_version(uow, code.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        code.id,
        INTAKE_CODE,
        [NewEvent(event_type=INTAKE_CODE_REVOKED, payload=silent({"reason": cmd.reason}))],
    )
    moved = move(uow, cmd, code.id, T_REVOKE)
    return CommandResult(
        stream_id=code.id, key=None, version=moved.version, events=[*done.events, *moved.events]
    )


# --- items -------------------------------------------------------------------------------------


def _clean_claim(value: Any) -> str | None:
    """One claim text: control and direction characters removed, trimmed, at most ``MAX_CLAIM``
    characters; ``None`` when nothing is left or the value is not text."""
    if not isinstance(value, str):
        return None
    cleaned = FORBIDDEN_TEXT.sub("", value).strip()[:MAX_CLAIM].strip()
    return cleaned or None


def _claim_of(body: str | None) -> dict[str, str] | None:
    """What the sender said about themselves: ``{name, company}`` from the answers ``claim_name``
    and ``claim_company`` of the stored body. ``claim_phone`` is never read. A body that is not the
    expected JSON gives ``None``."""
    if body is None:
        return None
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    answers: Any = data.get("answers") if isinstance(data, dict) else None  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(answers, list):
        return None
    wanted = {"claim_name": "name", "claim_company": "company"}
    claim: dict[str, str] = {}
    for entry in answers:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            continue
        asked: Any = entry.get("q")  # pyright: ignore[reportUnknownMemberType]
        slot = wanted.get(asked) if isinstance(asked, str) else None
        cleaned = _clean_claim(entry.get("value"))  # pyright: ignore[reportUnknownMemberType]
        if slot is not None and cleaned is not None:
            claim.setdefault(slot, cleaned)
    return claim or None


def _received_event(uow: UnitOfWork, item_id: str) -> str | None:
    found = uow.conn().execute(_RECEIVED_SQL, {"id": item_id}).scalar_one_or_none()
    return None if found is None else str(found)


def handle_accept_intake_item(uow: UnitOfWork, cmd: AcceptIntakeItem) -> CommandResult:
    """Pending to Accepted: run the controller's command as the controller, then record it, move
    the item, delete its body and purge it, all in the caller's unit of work."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = _load(uow, cmd, cmd.item_id, INTAKE_ITEM, PENDING)
    _require_state(item, "AcceptIntakeItem", PENDING)
    require_version(uow, item.id, cmd.expected_version)
    template = load_template(uow, str(item.row["template_id"]))
    if cmd.command_type not in (template.accepts_as or []):
        raise FormRuleError(MSG_NOT_ACCEPTED_AS)
    code_id = str(item.row["code_id"])
    conn = uow.conn()
    nested = run_nested_command(
        uow,
        command_type=cmd.command_type,
        args=cmd.command_args,
        actor=cmd.actor,
        scope=cmd.scope,
        source=f"intake:{code_id}",
        causation_id=_received_event(uow, item.id),
        correlation_id=cmd.correlation_id,
        holder=holder_for_actor(conn, cmd.actor),
    )
    claim = _claim_of(conn.execute(_BODY_SQL, {"id": item.id}).scalar_one_or_none())
    append(
        uow,
        cmd,
        item.id,
        INTAKE_ITEM,
        [
            NewEvent(
                event_type=INTAKE_ITEM_ACCEPTED,
                payload=silent(
                    {
                        "accepted_as": cmd.command_type,
                        "on_behalf_of_claim": claim,
                        "cause_event_id": nested.events[0].event_id if nested.events else None,
                    }
                ),
            )
        ],
    )
    moved = move(uow, cmd, item.id, T_ACCEPT)
    conn.execute(_DELETE_BODY_SQL, {"id": item.id})
    purged = append(
        uow,
        cmd,
        item.id,
        INTAKE_ITEM,
        [
            NewEvent(
                event_type=INTAKE_ITEM_PURGED,
                payload=silent({"purged_at": iso_utc(utcnow())}),
            )
        ],
    )
    return CommandResult(
        stream_id=item.id,
        key=None,
        version=purged.new_version,
        # the Accepted event holds the sender's claim: it stays in the ledger, not in a result
        events=[*moved.events, *purged.events],
    )


def handle_reject_intake_item(uow: UnitOfWork, cmd: RejectIntakeItem) -> CommandResult:
    """Pending to Rejected; the body stays until the retention purge."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = _load(uow, cmd, cmd.item_id, INTAKE_ITEM, PENDING)
    _require_state(item, "RejectIntakeItem", PENDING)
    require_version(uow, item.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        item.id,
        INTAKE_ITEM,
        [NewEvent(event_type=INTAKE_ITEM_REJECTED, payload=silent({"reason": cmd.reason}))],
    )
    moved = move(uow, cmd, item.id, T_REJECT)
    return CommandResult(
        stream_id=item.id, key=None, version=moved.version, events=[*done.events, *moved.events]
    )


__all__ = [
    "handle_accept_intake_item",
    "handle_issue_intake_code",
    "handle_reject_intake_item",
    "handle_revoke_intake_code",
]
