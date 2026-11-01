"""Which commands the viewer may run on a record now: the table and the hook (ADR-0010 addendum).

``RULES`` is the one source for two things that must not drift apart: the access of each command
(a test holds every row's ``word`` equal to the ``access`` of the command in
``commands.AWP_COMMANDS``)
and the label a screen shows for it. ``awp_actions`` is the hook the module gives
``ModuleSpec.actions``; it is a pure function of the record's own rows and ``holds``. S4 adds the
rows of the package types and the workflow states.

An offer is advice. The handler still checks the record's state and the access word when the
command runs. A WBS node, a path and an area have no workflow: a node and an area are *active* until
they are retired. Commands that need no record (define, create) are not offers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_core.actions import ActionOffer, Holds, Level
from tl_core.auth.module_roles import normalise_word

from tl_mod_awp.names import CWA, CWA_TABLE, PATH, WBS_NODE, WBS_NODE_TABLE

Check = Callable[[Connection, str], bool]

_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")
_NODE_RETIRED_SQL = text(f"SELECT retired FROM {WBS_NODE_TABLE} WHERE id = :id")
_CHILD_SQL = text(f"SELECT 1 FROM {WBS_NODE_TABLE} WHERE parent_id = :id LIMIT 1")
_CWA_RETIRED_SQL = text(f"SELECT retired FROM {CWA_TABLE} WHERE id = :id")


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


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer: its label, its access word and the record types it takes."""

    command: str  # the command model's class name, as in ``commands.AWP_COMMANDS``
    label: str  # plain words
    word: str  # the fine access word of the command (schema/settings/access-words.yaml)
    record_types: tuple[str, ...]
    check: Check = _always


RULES: tuple[Rule, ...] = (
    Rule("ReviseWbsNode", "Edit", "awp.wbs.configure", (WBS_NODE,), _active_node),
    Rule("MapWbsToCostCodes", "Map cost codes", "awp.wbs.configure", (WBS_NODE,), _active_leaf),
    Rule("MoveCwaInPath", "Move CWA", "awp.path.configure", (PATH,)),
    Rule("ReviseCwa", "Edit", "awp.cwa.edit", (CWA,), _active_cwa),
    # last: a retirement ends the use of the node or the area
    Rule("RetireWbsNode", "Retire", "awp.wbs.configure", (WBS_NODE,), _active_node),
    Rule("RetireCwa", "Retire", "awp.wbs.configure", (CWA,), _active_cwa),
)


def level_of(rule: Rule) -> Level:
    """The access level the rule's word asks for (``user`` or ``controller``)."""
    table_word = normalise_word(rule.word)
    if table_word == "controller":
        return "controller"
    return "user"


def awp_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this record now, in the order of ``RULES``."""
    record_type = conn.execute(_TYPE_SQL, {"id": record_id}).scalar_one_or_none()
    if record_type is None:
        return []
    return [
        ActionOffer(command=rule.command, label=rule.label)
        for rule in RULES
        if record_type in rule.record_types
        and holds(level_of(rule))
        and rule.check(conn, record_id)
    ]


__all__ = ["RULES", "Rule", "awp_actions", "level_of"]
