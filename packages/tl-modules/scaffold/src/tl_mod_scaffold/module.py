"""What the scaffold module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``scaffold`` in this package's ``pyproject.toml`` names
``spec``. Both record types are offline class ``none`` (a register entry and a tag are acts on the
authority): no ``offline_drafts``. ``proposable`` is empty and the module declares its commands and
its read router on the hooks (P2-I4B S2; ADR-0029).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from tl_mod_scaffold import MODULE
from tl_mod_scaffold.commands import (
    DesignScaffold,
    DismantleScaffold,
    ErectScaffold,
    InspectScaffold,
    ModifyScaffold,
    RegisterScaffold,
    ReleaseScaffold,
    RemoveScaffold,
    TagScaffoldGreen,
)
from tl_mod_scaffold.guards import not_removed
from tl_mod_scaffold.handlers.scaffold import (
    handle_design_scaffold,
    handle_dismantle_scaffold,
    handle_erect_scaffold,
    handle_inspect_scaffold,
    handle_modify_scaffold,
    handle_register_scaffold,
    handle_release_scaffold,
    handle_remove_scaffold,
    handle_tag_scaffold_green,
)
from tl_mod_scaffold.names import (
    DESIGN,
    DISMANTLE_WORD,
    ERECT,
    INSPECT,
    MODIFY_WORD,
    RECORD_TYPES,
    REGISTER,
    RELEASE,
    REMOVE,
    SCAFFOLD,
    TAG_GREEN,
)
from tl_mod_scaffold.projectors import ScaffoldProjector


@dataclass(frozen=True)
class ScaffoldCommand:
    """A command, its handler and its fine access word (the API reads ``model`` and ``access``)."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str


#: The word the API table reads for the module's row type.
ApiCommand = ScaffoldCommand

SCAFFOLD_COMMANDS: tuple[ScaffoldCommand, ...] = (
    ScaffoldCommand(RegisterScaffold, handle_register_scaffold, REGISTER),
    ScaffoldCommand(DesignScaffold, handle_design_scaffold, DESIGN),
    ScaffoldCommand(ErectScaffold, handle_erect_scaffold, ERECT),
    ScaffoldCommand(InspectScaffold, handle_inspect_scaffold, INSPECT),
    ScaffoldCommand(TagScaffoldGreen, handle_tag_scaffold_green, TAG_GREEN),
    ScaffoldCommand(ReleaseScaffold, handle_release_scaffold, RELEASE),
    ScaffoldCommand(ModifyScaffold, handle_modify_scaffold, MODIFY_WORD),
    ScaffoldCommand(DismantleScaffold, handle_dismantle_scaffold, DISMANTLE_WORD),
    ScaffoldCommand(RemoveScaffold, handle_remove_scaffold, REMOVE),
)

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A scaffold takes property values, links, files and the life of its links until it is Removed
#: (``guards.not_removed``). Its fields and state change only through the module's commands: not
#: ``UpdateRecord``, ``VoidRecord`` or ``TransitionWorkflow`` (ADR-0010 addendum 1). An inspection
#: takes none: it is a fact.
SCAFFOLD_GENERIC_COMMANDS = frozenset({"SetPsetValues", "AddLink", "AttachFile"}) | LINK_LIFE


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [ScaffoldProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={SCAFFOLD: SCAFFOLD_GENERIC_COMMANDS},
        generic_guards={(SCAFFOLD, c): not_removed for c in SCAFFOLD_GENERIC_COMMANDS},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in SCAFFOLD_COMMANDS},
        commands="tl_mod_scaffold.module:SCAFFOLD_COMMANDS",
        read_routers=("tl_api.routes.scaffold:router",),
        reports=("tl_mod_scaffold.report_rows:REPORTS",),
    )
