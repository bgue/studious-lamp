"""What the awp module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``awp`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector

from tl_mod_awp import MODULE
from tl_mod_awp.actions import awp_actions
from tl_mod_awp.commands import AWP_COMMANDS, CreateCwp
from tl_mod_awp.guards import iwp_not_closed, not_closed
from tl_mod_awp.handlers.cwp import handle_create_cwp
from tl_mod_awp.names import (
    CWA,
    CWP,
    EWP,
    IWP,
    PATH,
    PWP,
    RECORD_TYPES,
    SCOPE_ITEM,
    WBS_NODE,
)
from tl_mod_awp.projectors import CwaProjector, PathProjector, WbsProjector
from tl_mod_awp.projectors.cwp import cwp_projectors
from tl_mod_awp.projectors.iwp import iwp_projectors
from tl_mod_awp.projectors.rollup import rollup_projectors
from tl_mod_awp.projectors.scope import scope_item_projectors
from tl_mod_awp.readiness.projector import readiness_projectors

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: An area takes links, suggested links and a plot plan. Its name and place change only through
#: ``ReviseCwa``. A WBS node and the path take no generic command: the links of a node to its cost
#: codes are the module's (``by_module``, source ``rule``), so a person cannot retract them.
CWA_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
#: A package takes property values, links, files and the life of its links, until it is Closed or
#: Void (``guards.not_closed``). Its fields, its state and its allocation change only through the
#: module's commands; a void is the module's (``VoidCwp``), never ``VoidRecord``.
CWP_GENERIC_COMMANDS = (
    frozenset({"SetPsetValues", "AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
)
#: An IWP takes property values, links, files and the life of its links until it is Closed, Split or
#: Cancelled (``guards.iwp_not_closed``). Its fields, scope, pins and state change only through the
#: module's commands. A scope item takes links and the life of their links; the
#: links the module wrote (``belongs_to`` scope; source ``rule``) are not
#: retractable by a person (``tl_core.services.links``).
IWP_GENERIC_COMMANDS = (
    frozenset({"SetPsetValues", "AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
)
LINKED_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE
#: An owner package reference takes links and the life of its links.
PACKAGE_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE

#: What an agent may propose (ADR-0014 section 8): a new package. Accepting runs ``CreateCwp`` as
#: the accepting person, who needs ``awp.cwp.edit`` (a ``user`` word).
PROPOSABLE = (ProposableCommand("propose_cwp", CreateCwp, handle_create_cwp, "user"),)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    # cwp_projectors: S4 (CWP, EWPRef, PWPRef); rollup_projectors: S5 (cur_awp_rollup)
    return [
        WbsProjector(),
        PathProjector(),
        CwaProjector(),
        *cwp_projectors(),
        *rollup_projectors(),
        *iwp_projectors(),
        *scope_item_projectors(),
        *readiness_projectors(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            CWA: CWA_GENERIC_COMMANDS,
            WBS_NODE: frozenset(),
            PATH: frozenset(),
            CWP: CWP_GENERIC_COMMANDS,
            EWP: PACKAGE_GENERIC_COMMANDS,
            PWP: PACKAGE_GENERIC_COMMANDS,
            IWP: IWP_GENERIC_COMMANDS,
            SCOPE_ITEM: LINKED_GENERIC_COMMANDS,
        },
        generic_guards={
            **{(CWP, command): not_closed for command in CWP_GENERIC_COMMANDS},
            **{(IWP, command): iwp_not_closed for command in IWP_GENERIC_COMMANDS},
        },
        proposable=PROPOSABLE,
        # which of the commands a viewer may run on a record now; one table, actions.py
        actions={record_type: awp_actions for record_type in RECORD_TYPES},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in AWP_COMMANDS},
        offline_drafts={},  # no drafting commands (offline-classes spec, section 4)
    )
