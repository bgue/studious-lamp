"""Which commands the viewer may run on a record now: the table and the hook (ADR-0010 addendum).

``RULES`` is the one source for two things that must not drift apart: the access of each command
(a test holds every row's ``word`` equal to the ``access`` of the command in
``commands.AWP_COMMANDS``)
and the label a screen shows for it. ``awp_actions`` is the hook the module gives
``ModuleSpec.actions``; it is a pure function of the record's own rows and ``holds``. A row may
name the workflow states of a package in which it is offered (``states``); the handlers ask the same
table through ``states_for`` for the states a command takes, so the offer and the refusal cannot
drift.

An offer is advice. The handler still checks the record's state and the access word when the
command runs. A WBS node, a path and an area have no workflow: a node and an area are *active* until
they are retired. A package (CWP) is offered what its workflow state takes; an owner package
reference is offered its two commands until it is void. Commands that need no record (define,
create, record, request a rollup) are not offers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_core.actions import ActionOffer, Holds, Level
from tl_core.auth.module_roles import normalise_word

from tl_mod_awp.common import package_state, record_state
from tl_mod_awp.names import (
    CWA,
    CWA_TABLE,
    CWP,
    EWP,
    IWP,
    IWP_CHECK,
    IWP_DEVELOPMENT,
    IWP_DRAFT,
    IWP_EDITABLE,
    IWP_FIELD_COMPLETE,
    IWP_IN_PROGRESS,
    IWP_ISSUED,
    IWP_ON_HOLD,
    IWP_READY,
    PATH,
    PWP,
    ST_COMPLETE,
    ST_DEVELOPMENT,
    ST_EXECUTING,
    ST_PLANNED,
    ST_RELEASED,
    WBS_NODE,
    WBS_NODE_TABLE,
)

Check = Callable[[Connection, str], bool]

_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")
_NODE_RETIRED_SQL = text(f"SELECT retired FROM {WBS_NODE_TABLE} WHERE id = :id")
_CHILD_SQL = text(f"SELECT 1 FROM {WBS_NODE_TABLE} WHERE parent_id = :id LIMIT 1")
_CWA_RETIRED_SQL = text(f"SELECT retired FROM {CWA_TABLE} WHERE id = :id")
_VOIDED_SQL = text("SELECT voided FROM cur_core_record WHERE id = :id")

#: Every state a package can be voided from: all but Closed (Void is final).
LIVE_STATES = (ST_PLANNED, ST_DEVELOPMENT, ST_RELEASED, ST_EXECUTING, ST_COMPLETE)
#: The states an IWP can be cancelled in: every one but the final ones.
IWP_LIVE_STATES = (
    *IWP_EDITABLE,
    IWP_READY,
    IWP_ISSUED,
    IWP_IN_PROGRESS,
    IWP_FIELD_COMPLETE,
    IWP_ON_HOLD,
)


def _always(conn: Connection, record_id: str) -> bool:
    return True


def _active_node(conn: Connection, record_id: str) -> bool:
    found = conn.execute(_NODE_RETIRED_SQL, {"id": record_id}).scalar_one_or_none()
    return found is not None and not bool(found)


def _active_leaf(conn: Connection, record_id: str) -> bool:
    return _active_node(conn, record_id) and (
        conn.execute(_CHILD_SQL, {"id": record_id}).first() is None
    )


def _active_cwa(conn: Connection, record_id: str) -> bool:
    found = conn.execute(_CWA_RETIRED_SQL, {"id": record_id}).scalar_one_or_none()
    return found is not None and not bool(found)


def _not_void(conn: Connection, record_id: str) -> bool:
    found = conn.execute(_VOIDED_SQL, {"id": record_id}).scalar_one_or_none()
    return found is not None and not bool(found)


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer: its label, its access word and the record types it takes.

    ``states``: the workflow states of a package in which the command is offered and taken
    (``None``: the record has no workflow)."""

    command: str  # the command model's class name, as in ``commands.AWP_COMMANDS``
    label: str  # plain words
    word: str  # the fine access word of the command (schema/settings/access-words.yaml)
    record_types: tuple[str, ...]
    check: Check = _always
    states: tuple[str, ...] | None = None


RULES: tuple[Rule, ...] = (
    Rule("ReviseWbsNode", "Edit", "awp.wbs.configure", (WBS_NODE,), _active_node),
    Rule("MapWbsToCostCodes", "Map cost codes", "awp.wbs.configure", (WBS_NODE,), _active_leaf),
    Rule("MoveCwaInPath", "Move CWA", "awp.path.configure", (PATH,)),
    Rule("ReviseCwa", "Edit", "awp.cwa.edit", (CWA,), _active_cwa),
    # a package (CWP): one row per state and command (spec section 7)
    Rule("ReviseCwp", "Edit", "awp.cwp.edit", (CWP,), states=(ST_PLANNED, ST_DEVELOPMENT)),
    Rule(
        "AllocateCwpToWbs",
        "Allocate to WBS",
        "awp.cwp.edit",
        (CWP,),
        states=(ST_PLANNED, ST_DEVELOPMENT),
    ),
    Rule("StartCwpDevelopment", "Start development", "awp.cwp.edit", (CWP,), states=(ST_PLANNED,)),
    Rule(
        "ReleaseCwp",
        "Release for IWP development",
        "awp.cwp.release",
        (CWP,),
        states=(ST_DEVELOPMENT,),
    ),
    Rule("ReturnCwp", "Return to development", "awp.cwp.release", (CWP,), states=(ST_RELEASED,)),
    Rule("StartCwpExecution", "Start execution", "awp.cwp.edit", (CWP,), states=(ST_RELEASED,)),
    Rule("CompleteCwp", "Complete", "awp.cwp.edit", (CWP,), states=(ST_EXECUTING,)),
    Rule("CloseCwp", "Close", "awp.cwp.close", (CWP,), states=(ST_COMPLETE,)),
    Rule("ReopenCwp", "Reopen", "awp.cwp.close", (CWP,), states=(ST_COMPLETE,)),
    # the owner's package references have no workflow: not void is the state
    Rule("UpdateExternalPackage", "Update", "awp.package.edit", (EWP, PWP), _not_void),
    # an IWP: one row per state and command (field-work-packaging, "Records and states")
    Rule("AddIwpScope", "Add scope", "awp.iwp.edit", (IWP,), states=IWP_EDITABLE),
    Rule("RemoveIwpScope", "Remove scope", "awp.iwp.edit", (IWP,), states=IWP_EDITABLE),
    Rule("PinIwpDocument", "Pin a document", "awp.iwp.edit", (IWP,), states=IWP_EDITABLE),
    Rule("SplitIwp", "Split", "awp.iwp.edit", (IWP,), states=IWP_EDITABLE),
    Rule("StartIwpDevelopment", "Start development", "awp.iwp.edit", (IWP,), states=(IWP_DRAFT,)),
    Rule(
        "SendIwpToConstraintCheck",
        "Send to constraint check",
        "awp.iwp.edit",
        (IWP,),
        states=(IWP_DEVELOPMENT,),
    ),
    Rule(
        "ReturnIwpToDevelopment",
        "Return to development",
        "awp.iwp.edit",
        (IWP,),
        states=(IWP_CHECK,),
    ),
    Rule("SignOffIwp", "Sign off", "awp.iwp.signoff", (IWP,), states=(IWP_READY,)),
    Rule("IssueIwp", "Issue", "awp.iwp.issue", (IWP,), states=(IWP_READY,)),
    Rule(
        "HoldIwp",
        "Put on hold",
        "awp.iwp.hold",
        (IWP,),
        states=(IWP_READY, IWP_ISSUED, IWP_IN_PROGRESS),
    ),
    Rule("ReleaseHold", "Release the hold", "awp.iwp.hold", (IWP,), states=(IWP_ON_HOLD,)),
    # last: a retirement or a void ends the use of the node, the area or the package
    Rule("RetireWbsNode", "Retire", "awp.wbs.configure", (WBS_NODE,), _active_node),
    Rule("RetireCwa", "Retire", "awp.wbs.configure", (CWA,), _active_cwa),
    Rule("VoidCwp", "Void", "awp.void", (CWP,), states=LIVE_STATES),
    Rule("VoidExternalPackage", "Void", "awp.void", (EWP, PWP), _not_void),
    Rule("CancelIwp", "Cancel", "awp.void", (IWP,), states=IWP_LIVE_STATES),
)

_STATES: Mapping[tuple[str, str], tuple[str, ...]] = {
    (rule.command, record_type): rule.states
    for rule in RULES
    if rule.states is not None
    for record_type in rule.record_types
}


def states_for(command: str, record_type: str) -> tuple[str, ...]:
    """The workflow states in which ``command`` takes a record of ``record_type`` (``KeyError`` for
    a pair the table does not hold: a handler asking for a rule that is not written is a bug)."""
    return _STATES[(command, record_type)]


def level_of(rule: Rule) -> Level:
    """The access level the rule's word asks for (``user`` or ``controller``)."""
    table_word = normalise_word(rule.word)
    if table_word == "controller":
        return "controller"
    return "user"


def _state_of(conn: Connection, record_id: str, record_type: str) -> str | None:
    """The workflow state of a record whose type has one (``None`` for the others)."""
    if record_type == CWP:
        return package_state(conn, record_id)
    if record_type == IWP:
        return record_state(conn, record_id, IWP_DRAFT)
    return None


def awp_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this record now, in the order of ``RULES``."""
    record_type = conn.execute(_TYPE_SQL, {"id": record_id}).scalar_one_or_none()
    if record_type is None:
        return []
    state = _state_of(conn, record_id, record_type)
    return [
        ActionOffer(command=rule.command, label=rule.label)
        for rule in RULES
        if record_type in rule.record_types
        and (rule.states is None or state in rule.states)
        and holds(level_of(rule))
        and rule.check(conn, record_id)
    ]


__all__ = ["RULES", "Rule", "awp_actions", "level_of", "states_for"]
