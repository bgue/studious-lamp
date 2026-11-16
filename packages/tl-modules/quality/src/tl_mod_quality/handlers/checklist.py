"""Checklist commands: create, edit, publish, retire, revise (P2-INSP S2).

A checklist is one record of ``quality.Checklist``. It is edited in Draft only; a Published one
never changes (a change is a new version made by ``ReviseChecklist``, which supersedes it). Every
state move is a ``by_module`` workflow transition run in the same unit of work as the module's own
event. Refusals use fixed messages and name the state, never a cell of the input.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_quality.actions import states_for
from tl_mod_quality.commands import CHECKLIST_EDIT_FIELDS
from tl_mod_quality.errors import ChecklistRuleError, ChecklistStateError
from tl_mod_quality.guards import MSG_RETIRED
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
)
from tl_mod_quality.insp_rules import validate_questions
from tl_mod_quality.names import (
    CHECKLIST,
    CHECKLIST_CREATED,
    CHECKLIST_EDITED,
    CHECKLIST_PUBLISHED,
    CHECKLIST_RETIRED,
    CHECKLIST_TABLE,
    DRAFT,
    PUBLISHED,
    RETIRED,
    T_PUBLISH,
    T_RETIRE,
)

if TYPE_CHECKING:
    from tl_mod_quality.commands import (
        CreateChecklist,
        EditChecklist,
        PublishChecklist,
        RetireChecklist,
        ReviseChecklist,
    )

MSG_NOTHING = "nothing to change"
MSG_NOT_READY = "the question list cannot be published: "
MSG_REVISED = "a revision of this checklist already exists"
_ROW_SQL = text(f"SELECT * FROM {CHECKLIST_TABLE} WHERE id = :id")
_REVISION_SQL = text(
    f"SELECT r.id FROM {CHECKLIST_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.supersedes_id = :id AND r.voided = :no AND COALESCE(r.status, :draft) <> :retired"
)
#: The edit fields held on the typed row; the title is the envelope's.
_ENVELOPE = {"title": "title"}


def as_list(value: Any) -> list[dict[str, Any]]:
    """The questions of a ``questions_json`` cell (text on SQLite, parsed on Postgres)."""
    loaded = json.loads(value) if isinstance(value, (str, bytes)) else value
    return list(loaded or [])


@dataclass(frozen=True)
class Checklist:
    """A checklist as the handlers read it: the envelope, the typed row and the state."""

    ref: RecordRef
    state: str
    row: dict[str, Any]

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def key(self) -> str:
        return self.ref.key or ""

    @property
    def questions(self) -> list[dict[str, Any]]:
        return as_list(self.row["questions_json"])


def load_checklist(uow: UnitOfWork, scope: str, checklist_id: str) -> Checklist:
    """The checklist; ``RecordNotFoundError`` (the same words) when it is hidden, absent, in
    another project or not a checklist."""
    ref = load_record(uow, scope, checklist_id, (CHECKLIST,))
    row = uow.conn().execute(_ROW_SQL, {"id": ref.id}).mappings().first()
    if row is None:
        raise LookupError(f"no checklist row for {ref.id}")
    return Checklist(ref=ref, state=record_state(uow, ref.id, DRAFT), row=dict(row))


def require_state(checklist: Checklist, command: str) -> None:
    """The checklist is not retired and is in a state ``command`` takes (``actions.RULES``)."""
    if checklist.state == RETIRED:
        raise ChecklistStateError(MSG_RETIRED)
    needed = states_for(command, CHECKLIST)
    if checklist.state not in needed:
        raise ChecklistStateError(
            f"a checklist that is {checklist.state} does not take {command}; "
            f"it needs {' or '.join(needed)}"
        )


def _today() -> str:
    return utcnow().date().isoformat()


def _created(
    questions: list[dict[str, Any]], discipline: str | None, version: int, supersedes: str | None
) -> NewEvent:
    return NewEvent(
        event_type=CHECKLIST_CREATED,
        payload=silent(
            {
                "discipline": discipline,
                "questions": questions,
                "question_count": len(questions),
                "version": version,
                "supersedes_id": supersedes,
            }
        ),
    )


def handle_create_checklist(uow: UnitOfWork, cmd: CreateChecklist) -> CommandResult:
    """Create a checklist in Draft, version 1, numbered per project."""
    require_project(cmd)
    cmd = correlated(cmd)
    return create_module_record(
        uow,
        cmd,
        record_type=CHECKLIST,
        title=cmd.title,
        key=None,
        extra_events=[_created(cmd.questions, cmd.discipline, 1, None)],
    )


def handle_edit_checklist(uow: UnitOfWork, cmd: EditChecklist) -> CommandResult:
    """Change fields of a Draft checklist."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_checklist(uow, cmd.scope, cmd.checklist)
    require_state(item, "EditChecklist")
    require_version(uow, item.id, cmd.expected_version)
    current = {
        "title": item.ref.title,
        "discipline": item.row["discipline"],
        "questions": item.questions,
    }
    changes: dict[str, list[Any]] = {}
    for field in [f for f in CHECKLIST_EDIT_FIELDS if f in cmd.model_fields_set]:
        new = getattr(cmd, field)
        if new != current[field]:
            changes[field] = [current[field], new]
    if not changes:
        raise ChecklistRuleError(MSG_NOTHING)
    events: list[NewEvent] = []
    if "title" in changes:
        events.append(
            NewEvent(event_type="Record.Updated", payload={"changes": {"title": changes["title"]}})
        )
    events.append(NewEvent(event_type=CHECKLIST_EDITED, payload=silent({"changes": changes})))
    done = append(uow, cmd, item.id, CHECKLIST, events)
    return CommandResult(
        stream_id=item.id, key=item.key, version=done.new_version, events=done.events
    )


def _step(
    uow: UnitOfWork, cmd: Command, record_id: str, transition: str, event_type: str, on: str
) -> CommandResult:
    """Append the module's event, then run the workflow transition (one unit of work)."""
    column = "published_on" if event_type == CHECKLIST_PUBLISHED else "retired_on"
    done = append(
        uow,
        cmd,
        record_id,
        CHECKLIST,
        [NewEvent(event_type=event_type, payload=silent({column: on}))],
    )
    moved = move(uow, cmd, record_id, transition)
    return CommandResult(
        stream_id=record_id,
        key=None,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_publish_checklist(uow: UnitOfWork, cmd: PublishChecklist) -> CommandResult:
    """Draft to Published. A revision retires the Published version it supersedes in the same
    unit of work, so there is never a gap."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_checklist(uow, cmd.scope, cmd.checklist)
    require_state(item, "PublishChecklist")
    problems = validate_questions(item.questions)
    if problems:
        raise ChecklistRuleError(MSG_NOT_READY + "; ".join(problems))
    require_version(uow, item.id, cmd.expected_version)
    today = _today()
    done = _step(uow, cmd, item.id, T_PUBLISH, CHECKLIST_PUBLISHED, today)
    events = list(done.events)
    older = item.row["supersedes_id"]
    if older is not None and record_state(uow, str(older), DRAFT) == PUBLISHED:
        events.extend(_step(uow, cmd, str(older), T_RETIRE, CHECKLIST_RETIRED, today).events)
    return CommandResult(stream_id=item.id, key=item.key, version=done.version, events=events)


def handle_retire_checklist(uow: UnitOfWork, cmd: RetireChecklist) -> CommandResult:
    """Draft or Published to Retired, the final state."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_checklist(uow, cmd.scope, cmd.checklist)
    require_state(item, "RetireChecklist")
    require_version(uow, item.id, cmd.expected_version)
    done = _step(uow, cmd, item.id, T_RETIRE, CHECKLIST_RETIRED, _today())
    return CommandResult(stream_id=item.id, key=item.key, version=done.version, events=done.events)


def handle_revise_checklist(uow: UnitOfWork, cmd: ReviseChecklist) -> CommandResult:
    """Copy a Published checklist as a new Draft, version n+1, ``supersedes_id`` the old one."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_checklist(uow, cmd.scope, cmd.checklist)
    require_state(item, "ReviseChecklist")
    require_version(uow, item.id, cmd.expected_version)
    params = {"id": item.id, "no": False, "draft": DRAFT, "retired": RETIRED}
    if uow.conn().execute(_REVISION_SQL, params).first() is not None:
        raise ChecklistStateError(MSG_REVISED)
    return create_module_record(
        uow,
        cmd,
        record_type=CHECKLIST,
        title=item.ref.title,
        key=None,
        extra_events=[
            _created(
                item.questions,
                item.row["discipline"],
                int(item.row["checklist_version"]) + 1,
                item.id,
            )
        ],
    )


__all__ = [
    "Checklist",
    "as_list",
    "handle_create_checklist",
    "handle_edit_checklist",
    "handle_publish_checklist",
    "handle_retire_checklist",
    "handle_revise_checklist",
    "load_checklist",
]
