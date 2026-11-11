"""Punch commands: raise, edit, clear, verify, reopen, void (P2-PUNCH S2).

A punch item is one record of ``quality.PunchItem``. Every state move is a ``by_module`` workflow
transition run in the same unit of work as the module's own event. Refusals use fixed messages: an
id the viewer may not read, one in another project and one that does not exist answer alike. Who
may act is checked here after the platform checked the access word: the raiser, the assignee or a
verifier edits; nobody verifies what they cleared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, holds_word, normalise_word
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_quality import MODULE
from tl_mod_quality.actions import states_for
from tl_mod_quality.commands import EDIT_FIELDS
from tl_mod_quality.errors import PunchRuleError, PunchStateError
from tl_mod_quality.guards import require_not_void
from tl_mod_quality.handlers.common import (
    RecordRef,
    append,
    correlated,
    load_record,
    move,
    record_state,
    require_project,
    require_version,
    silent,
    valid_time,
)
from tl_mod_quality.names import (
    OPEN,
    PUNCH_CLEARED,
    PUNCH_EDITED,
    PUNCH_ITEM,
    PUNCH_ITEM_TABLE,
    PUNCH_RAISED,
    PUNCH_REOPENED,
    PUNCH_VERIFIED,
    PUNCH_VOIDED,
    RAISED_AGAINST,
    RULE_LINK_SOURCE,
    T_CLEAR,
    T_REOPEN,
    T_VERIFY,
    T_VOID,
    VERIFY,
)

if TYPE_CHECKING:
    from tl_mod_quality.commands import (
        ClearPunchItem,
        EditPunchItem,
        RaisePunchItem,
        ReopenPunchItem,
        VerifyPunchItem,
        VoidPunchItem,
    )

MSG_NOT_PARTY = "only the raiser, the assignee or a verifier may edit a punch item"
MSG_SELF_VERIFY = "the person who cleared a punch item may not verify it"
MSG_NOTHING = "nothing to change"
_ROW_SQL = text(f"SELECT * FROM {PUNCH_ITEM_TABLE} WHERE id = :id")
#: The edit fields held on the typed row; the subject and the description are the envelope's.
_ENVELOPE = {"subject": "title", "description": "description"}


@dataclass(frozen=True)
class PunchItem:
    """A punch item as the handlers read it: the envelope, the typed row and the state."""

    ref: RecordRef
    state: str
    row: dict[str, Any]

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def key(self) -> str:
        return self.ref.key or ""


def load_punch_item(uow: UnitOfWork, scope: str, item_id: str) -> PunchItem:
    """The punch item; ``RecordNotFoundError`` (the same words) when it is hidden, absent, in
    another project, voided or not a punch item."""
    ref = load_record(uow, scope, item_id, (PUNCH_ITEM,))
    row = uow.conn().execute(_ROW_SQL, {"id": ref.id}).mappings().first()
    if row is None:
        raise LookupError(f"no punch item row for {ref.id}")
    return PunchItem(ref=ref, state=record_state(uow, ref.id, OPEN), row=dict(row))


def require_state(item: PunchItem, command: str) -> None:
    """The item is not void and is in a state ``command`` takes (``actions.RULES``)."""
    require_not_void(item.state)
    needed = states_for(command)
    if item.state not in needed:
        raise PunchStateError(
            f"a punch item that is {item.state} does not take {command}; "
            f"it needs {' or '.join(needed)}"
        )


def _holds_verify(uow: UnitOfWork, cmd: Command) -> bool:
    conn = uow.conn()
    return holds_word(
        conn,
        holder_for_actor(conn, cmd.actor),
        scope=cmd.scope,
        module=MODULE,
        word=normalise_word(VERIFY),
    )


def handle_raise_punch_item(uow: UnitOfWork, cmd: RaisePunchItem) -> CommandResult:
    """Raise a punch item in state Open, numbered per project, with a ``raised_against`` link to
    the record it came from. ``raised_by`` is the actor."""
    require_project(cmd)
    cmd = correlated(cmd)
    source_id = (
        None if cmd.from_record_id is None else load_record(uow, cmd.scope, cmd.from_record_id).id
    )
    made = create_module_record(
        uow,
        cmd,
        record_type=PUNCH_ITEM,
        title=cmd.subject,
        description=cmd.description,
        key=None,
        extra_events=[
            NewEvent(
                event_type=PUNCH_RAISED,
                payload=silent(
                    {
                        "area": cmd.area,
                        "system": cmd.system,
                        "due_on": cmd.due_on,
                        "category": cmd.category,
                        "assignee": cmd.assignee,
                        "raised_by": cmd.actor,
                        "source_id": source_id,
                    }
                ),
            )
        ],
    )
    events = list(made.events)
    if source_id is not None:
        linked = handle_add_link(
            uow,
            AddLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                from_id=made.stream_id,
                to_id=source_id,
                relation=RAISED_AGAINST,
                link_source=RULE_LINK_SOURCE,
            ),
            by_module=True,
        )
        events.extend(linked.events)
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=events
    )


def _current(item: PunchItem, field: str) -> Any:
    return item.row.get(field) if field not in _ENVELOPE else _envelope(item, field)


def _envelope(item: PunchItem, field: str) -> Any:
    return item.ref.title if field == "subject" else item.ref.description


def handle_edit_punch_item(uow: UnitOfWork, cmd: EditPunchItem) -> CommandResult:
    """Change fields of an Open punch item (the raiser, the assignee or a verifier)."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_punch_item(uow, cmd.scope, cmd.punch_item)
    require_state(item, "EditPunchItem")
    party = cmd.actor in (item.row["raised_by"], item.row["assignee"])
    if not party and not _holds_verify(uow, cmd):
        raise ForbiddenError(MSG_NOT_PARTY)
    require_version(uow, item.id, cmd.expected_version)
    changes: dict[str, list[Any]] = {}
    for field in [f for f in EDIT_FIELDS if f in cmd.model_fields_set]:
        new, old = getattr(cmd, field), _current(item, field)
        if new != old:
            changes[field] = [old, new]
    if not changes:
        raise PunchRuleError(MSG_NOTHING)
    events: list[NewEvent] = []
    envelope = {f: c for f, c in changes.items() if f in _ENVELOPE}
    if envelope:
        events.append(
            NewEvent(
                event_type="Record.Updated",
                payload={"changes": {_ENVELOPE[f]: pair for f, pair in envelope.items()}},
            )
        )
    events.append(NewEvent(event_type=PUNCH_EDITED, payload=silent({"changes": changes})))
    done = append(uow, cmd, item.id, PUNCH_ITEM, events)
    return CommandResult(
        stream_id=item.id, key=item.key, version=done.new_version, events=done.events
    )


def _step(
    uow: UnitOfWork,
    cmd: Any,
    item: PunchItem,
    transition: str,
    event_type: str,
    payload: dict[str, Any],
) -> CommandResult:
    """Append the module's event, then run the workflow transition (one unit of work)."""
    done = append(
        uow, cmd, item.id, PUNCH_ITEM, [NewEvent(event_type=event_type, payload=silent(payload))]
    )
    moved = move(uow, cmd, item.id, transition)
    return CommandResult(
        stream_id=item.id,
        key=item.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_clear_punch_item(uow: UnitOfWork, cmd: ClearPunchItem) -> CommandResult:
    """Open to Cleared; ``cleared_by`` is the actor, ``at`` the time the work was done."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_punch_item(uow, cmd.scope, cmd.punch_item)
    require_state(item, "ClearPunchItem")
    require_version(uow, item.id, cmd.expected_version)
    at = valid_time(cmd.at, item.ref.created_on)
    return _step(
        uow, cmd, item, T_CLEAR, PUNCH_CLEARED, {"by": cmd.actor, "note": cmd.note, "at": at}
    )


def handle_verify_punch_item(uow: UnitOfWork, cmd: VerifyPunchItem) -> CommandResult:
    """Cleared to Verified, by someone other than the person who cleared it."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_punch_item(uow, cmd.scope, cmd.punch_item)
    require_state(item, "VerifyPunchItem")
    if cmd.actor == item.row["cleared_by"]:
        raise ForbiddenError(MSG_SELF_VERIFY)
    require_version(uow, item.id, cmd.expected_version)
    at = valid_time(cmd.at, item.ref.created_on)
    return _step(uow, cmd, item, T_VERIFY, PUNCH_VERIFIED, {"by": cmd.actor, "at": at})


def handle_reopen_punch_item(uow: UnitOfWork, cmd: ReopenPunchItem) -> CommandResult:
    """Cleared or Verified back to Open; the projector resets the cleared and verified columns."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_punch_item(uow, cmd.scope, cmd.punch_item)
    require_state(item, "ReopenPunchItem")
    require_version(uow, item.id, cmd.expected_version)
    return _step(uow, cmd, item, T_REOPEN, PUNCH_REOPENED, {"by": cmd.actor, "reason": cmd.reason})


def handle_void_punch_item(uow: UnitOfWork, cmd: VoidPunchItem) -> CommandResult:
    """Open or Cleared to Void, the final state."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_punch_item(uow, cmd.scope, cmd.punch_item)
    require_state(item, "VoidPunchItem")
    require_version(uow, item.id, cmd.expected_version)
    return _step(uow, cmd, item, T_VOID, PUNCH_VOIDED, {"by": cmd.actor, "reason": cmd.reason})


__all__ = [
    "PunchItem",
    "handle_clear_punch_item",
    "handle_edit_punch_item",
    "handle_raise_punch_item",
    "handle_reopen_punch_item",
    "handle_verify_punch_item",
    "handle_void_punch_item",
]
