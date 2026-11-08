"""Which commands the viewer may run on a record now: the table and the hook (ADR-0010 addendum).

``RULES`` is the one source for three things that must not drift apart: the access of each command
(a test holds every row's ``word`` equal to the ``access`` of the command in
``module.REQUISITIONS_COMMANDS``), the label a screen shows for it, and the workflow states in which
the handlers take it (``states_for``). ``requisitions_actions`` is the hook the module gives
``ModuleSpec.actions``: a pure function of the record's state and ``holds``. A requisition is
offered the commands on itself; the work order commands are offered on the work order. An offer is
advice: the handler still checks the state, who may act (the requester edits and cancels their own;
nobody approves their own) and the access word when the command runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_core.actions import ActionOffer, Holds, Level
from tl_core.auth.module_roles import normalise_word

from tl_mod_requisitions.names import (
    APPROVE,
    ASSIGN,
    CANCEL,
    CLOSE,
    COMPLETE,
    EDIT,
    REJECT,
    REQUISITION_TYPES,
    SCHEDULE,
    ST_APPROVED,
    ST_DONE,
    ST_IN_PROGRESS,
    ST_OPEN,
    ST_REQUESTED,
    ST_SCHEDULED,
    START,
    WORK_ORDER,
)

_STATE_SQL = text("SELECT type, status, voided FROM cur_core_record WHERE id = :id")


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer: its label, its access word, the record types it takes and
    the workflow states in which it is offered and taken."""

    command: str  # the command model's class name, as in ``module.REQUISITIONS_COMMANDS``
    label: str
    word: str  # the fine access word (schema/settings/access-words.yaml)
    record_types: tuple[str, ...]
    states: tuple[str, ...]


RULES: tuple[Rule, ...] = (
    Rule("EditRequisition", "Edit", EDIT, REQUISITION_TYPES, (ST_REQUESTED,)),
    Rule("ApproveRequisition", "Approve", APPROVE, REQUISITION_TYPES, (ST_REQUESTED,)),
    Rule("RejectRequisition", "Reject", REJECT, REQUISITION_TYPES, (ST_REQUESTED,)),
    Rule("CancelRequisition", "Cancel", CANCEL, REQUISITION_TYPES, (ST_REQUESTED, ST_APPROVED)),
    Rule("ScheduleWorkOrder", "Schedule", SCHEDULE, (WORK_ORDER,), (ST_OPEN,)),
    Rule("AssignWorkOrder", "Assign", ASSIGN, (WORK_ORDER,), (ST_OPEN, ST_SCHEDULED)),
    Rule("StartWorkOrder", "Start work", START, (WORK_ORDER,), (ST_SCHEDULED,)),
    Rule("CompleteWorkOrder", "Complete", COMPLETE, (WORK_ORDER,), (ST_IN_PROGRESS,)),
    Rule("CloseWorkOrder", "Close", CLOSE, (WORK_ORDER,), (ST_DONE,)),
)

_STATES: Mapping[tuple[str, str], tuple[str, ...]] = {
    (rule.command, record_type): rule.states for rule in RULES for record_type in rule.record_types
}


def states_for(command: str, record_type: str) -> tuple[str, ...]:
    """The workflow states in which ``command`` takes a record of ``record_type`` (``KeyError`` for
    a pair the table does not hold: a handler asking for a rule that is not written is a bug)."""
    return _STATES[(command, record_type)]


def level_of(rule: Rule) -> Level:
    """The access level the rule's word asks for (``user`` or ``controller``)."""
    return "controller" if normalise_word(rule.word) == "controller" else "user"


def requisitions_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this record now, in the order of ``RULES``."""
    row = conn.execute(_STATE_SQL, {"id": record_id}).first()
    if row is None or bool(row.voided):
        return []
    initial = ST_OPEN if row.type == WORK_ORDER else ST_REQUESTED
    state = initial if row.status is None else str(row.status)
    return [
        ActionOffer(command=rule.command, label=rule.label)
        for rule in RULES
        if row.type in rule.record_types and state in rule.states and holds(level_of(rule))
    ]


__all__ = ["RULES", "Rule", "level_of", "requisitions_actions", "states_for"]
