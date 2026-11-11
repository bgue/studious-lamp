"""Which commands the viewer may run on a punch item now: the table and the hook (ADR-0010).

``RULES`` is the one source for three things that must not drift apart: the access of each command
(a test holds every row's ``level`` equal to the table word of the command's access word), the label
a screen shows for it, and the workflow states in which the handlers take it (``states_for``).
``punch_actions`` is the hook the module gives ``ModuleSpec.actions``: a pure function of the
record's state and ``holds``. An offer is advice: the handler still checks the state, who may act
(the raiser, the assignee or a verifier edits; nobody verifies what they cleared) and the access
word when the command runs. ``RaisePunchItem`` needs no record and is not an offer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_core.actions import ActionOffer, Holds, Level

from tl_mod_quality.names import CLEARED, OPEN, PUNCH_ITEM, VERIFIED

_STATE_SQL = text("SELECT type, status, voided FROM cur_core_record WHERE id = :id")


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer: its label, its access level, the record types it takes and
    the workflow states in which it is offered and taken."""

    command: str  # the command model's class name, as in ``module.PUNCH_COMMANDS``
    label: str
    level: Level
    record_types: tuple[str, ...]
    states: tuple[str, ...]


RULES: tuple[Rule, ...] = (
    Rule("EditPunchItem", "Edit", "user", (PUNCH_ITEM,), (OPEN,)),
    Rule("ClearPunchItem", "Clear", "user", (PUNCH_ITEM,), (OPEN,)),
    Rule("VerifyPunchItem", "Verify", "controller", (PUNCH_ITEM,), (CLEARED,)),
    Rule("ReopenPunchItem", "Reopen", "controller", (PUNCH_ITEM,), (CLEARED, VERIFIED)),
    Rule("VoidPunchItem", "Void", "controller", (PUNCH_ITEM,), (OPEN, CLEARED)),
)

_STATES: Mapping[tuple[str, str], tuple[str, ...]] = {
    (rule.command, record_type): rule.states for rule in RULES for record_type in rule.record_types
}


def states_for(command: str, record_type: str = PUNCH_ITEM) -> tuple[str, ...]:
    """The workflow states in which ``command`` takes a record of ``record_type`` (``KeyError``
    for a pair the table does not hold: a handler asking for a rule not written is a bug)."""
    return _STATES[(command, record_type)]


def punch_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this punch item now, in the order of ``RULES``."""
    row = conn.execute(_STATE_SQL, {"id": record_id}).first()
    if row is None or bool(row.voided):
        return []
    state = OPEN if row.status is None else str(row.status)
    return [
        ActionOffer(command=rule.command, label=rule.label)
        for rule in RULES
        if row.type in rule.record_types and state in rule.states and holds(rule.level)
    ]


__all__ = ["RULES", "Rule", "punch_actions", "states_for"]
