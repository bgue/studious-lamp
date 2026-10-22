"""Which actions may a viewer take on a record now (P1-UX2-S1; ADR-0010 addendum).

The question is answered by the module that owns the record type: its ``ModuleSpec.actions`` maps a
record type to a hook that is a pure function over the module's own rows and ``holds``. The core
decides three things only, in this order:

1. **Visibility first.** A record the viewer may not read (ADR-0016) and a record that does not
   exist raise the same ``RecordNotFoundError`` with the same text, before any hook runs.
2. **An agent proposes, it never changes a record.** An actor ``agent:*`` is offered nothing.
3. **The module's hook** for the record's type; a type with no hook is offered nothing.

An offer names a command of the module's own table and a label in plain words. It is advice for a
screen, not a permission: the command still checks its state and its access word when it runs, and
a refusal is shown as it is. The viewer is the one set by the entry point (``use_viewer``), as for
every read.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Connection, text

from tl_core import confidentiality
from tl_core.modules import load_modules
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

#: The access a command asks for: ``user`` is any signed-in person.
Level = Literal["user", "controller", "admin"]
#: Whether the viewer holds a level: the decision the API authorizer or the embedded gates make.
Holds = Callable[[Level], bool]


class ActionOffer(BaseModel):
    """One thing the viewer may do: the module command to run and its label in plain words."""

    command: str
    label: str


class RecordActions(BaseModel):
    """The actions offered on one record. ``state`` is the workflow state the record is in now
    (``Void`` once voided; ``None`` while a record has not moved from its initial state)."""

    record_id: str
    state: str | None
    actions: list[ActionOffer]


#: ``(conn, record_id, holds)`` to the offers for a record the viewer may read.
ActionsHook = Callable[[Connection, str, Holds], list[ActionOffer]]

_RECORD_SQL = text("SELECT type, status, voided FROM cur_core_record WHERE id = :id")
_AGENT_PREFIX = "agent:"


def allowed_actions(uow: UnitOfWork, record_id: str, *, actor: str, holds: Holds) -> RecordActions:
    """What ``actor`` may do on the record now. Raises ``RecordNotFoundError`` for a record that
    is missing or hidden from the viewer, with the same text for both."""
    conn = uow.conn()
    confidentiality.require_visible(conn, record_id)
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    state: str | None = "Void" if bool(row.voided) else row.status
    if actor.startswith(_AGENT_PREFIX):
        return RecordActions(record_id=record_id, state=state, actions=[])
    for spec in load_modules():
        hook = spec.actions.get(row.type)
        if hook is not None:
            return RecordActions(
                record_id=record_id, state=state, actions=hook(conn, record_id, holds)
            )
    return RecordActions(record_id=record_id, state=state, actions=[])
