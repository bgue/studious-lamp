"""What the awp module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``awp`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_awp import MODULE
from tl_mod_awp.actions import awp_actions
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.names import CWA, PATH, RECORD_TYPES, WBS_NODE
from tl_mod_awp.projectors import CwaProjector, PathProjector, WbsProjector

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: An area takes links, suggested links and a plot plan. Its name and place change only through
#: ``ReviseCwa``. A WBS node and the path take no generic command: the links of a node to its cost
#: codes are the module's (``by_module``, source ``rule``), so a person cannot retract them.
CWA_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [WbsProjector(), PathProjector(), CwaProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={CWA: CWA_GENERIC_COMMANDS, WBS_NODE: frozenset(), PATH: frozenset()},
        # which of the commands a viewer may run on a record now; one table, actions.py
        actions={record_type: awp_actions for record_type in RECORD_TYPES},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in AWP_COMMANDS},
        offline_drafts={},  # no drafting commands (offline-classes spec, section 4)
    )
