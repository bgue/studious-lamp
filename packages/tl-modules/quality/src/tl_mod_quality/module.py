"""What the quality module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``quality`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process. ``PunchItem`` is ``draft_only``: a walkdown raises
items offline (``RaisePunchItem`` is the draft); clearing, verifying, reopening and voiding are
central.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tl_core.modules import ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from tl_mod_quality import MODULE
from tl_mod_quality.actions import punch_actions
from tl_mod_quality.commands import (
    ClearPunchItem,
    EditPunchItem,
    RaisePunchItem,
    ReopenPunchItem,
    VerifyPunchItem,
    VoidPunchItem,
)
from tl_mod_quality.guards import not_void
from tl_mod_quality.handlers.punch import (
    handle_clear_punch_item,
    handle_edit_punch_item,
    handle_raise_punch_item,
    handle_reopen_punch_item,
    handle_verify_punch_item,
    handle_void_punch_item,
)
from tl_mod_quality.names import (
    CLEAR,
    EDIT,
    PUNCH_ITEM,
    RAISE,
    RECORD_TYPES,
    REOPEN,
    VERIFY,
    VOID_WORD,
)
from tl_mod_quality.projectors import PunchItemProjector


@dataclass(frozen=True)
class PunchCommand:
    """A command, its handler and its fine access word (the API reads ``model`` and ``access``)."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str


#: The word the API table (``tl_api.commands``) reads for the module's row type.
ApiCommand = PunchCommand

PUNCH_COMMANDS: tuple[PunchCommand, ...] = (
    PunchCommand(RaisePunchItem, handle_raise_punch_item, RAISE),
    PunchCommand(EditPunchItem, handle_edit_punch_item, EDIT),
    PunchCommand(ClearPunchItem, handle_clear_punch_item, CLEAR),
    PunchCommand(VerifyPunchItem, handle_verify_punch_item, VERIFY),
    PunchCommand(ReopenPunchItem, handle_reopen_punch_item, REOPEN),
    PunchCommand(VoidPunchItem, handle_void_punch_item, VOID_WORD),
)

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A punch item takes property values, links, files and the life of its links until it is Void
#: (``guards.not_void``). Its fields and state change only through the module's commands: not
#: ``UpdateRecord``, ``VoidRecord`` or ``TransitionWorkflow`` (ADR-0010 addendum 1).
PUNCH_GENERIC_COMMANDS = frozenset({"SetPsetValues", "AddLink", "AttachFile"}) | LINK_LIFE

#: What an agent may propose (ADR-0014 section 8, ADR-0027): a new punch item. Accepting runs
#: ``RaisePunchItem`` as the accepting person, who needs ``quality.punch.raise`` (a ``user`` word).
#: The other five commands are in ``tests/tools/proposable_exclusions.toml`` with the reason.
PROPOSABLE = (
    ProposableCommand("propose_punch_item", RaisePunchItem, handle_raise_punch_item, "user"),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [PunchItemProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={PUNCH_ITEM: PUNCH_GENERIC_COMMANDS},
        generic_guards={(PUNCH_ITEM, c): not_void for c in PUNCH_GENERIC_COMMANDS},
        proposable=PROPOSABLE,
        actions={PUNCH_ITEM: punch_actions},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in PUNCH_COMMANDS},
        # a walkdown raises items offline; each is numbered when it syncs (offline classes)
        offline_drafts={PUNCH_ITEM: frozenset({"RaisePunchItem"})},
    )
