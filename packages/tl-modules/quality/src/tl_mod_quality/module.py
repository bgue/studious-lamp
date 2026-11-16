"""What the quality module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``quality`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process. ``PunchItem`` is ``draft_only``: a walkdown raises
items offline (``RaisePunchItem`` is the draft); clearing, verifying, reopening and voiding are
central. ``Inspection`` is ``draft_only`` too: ``RecordInspectionResult`` is its draft. The
``commands`` hook names ``QUALITY_COMMANDS``: the six punch commands then the eleven of checklists
and inspections. ``PUNCH_COMMANDS`` stays as it was (the terminal's embedded client imports it).
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
    CancelInspection,
    ClearPunchItem,
    CreateChecklist,
    EditChecklist,
    EditPunchItem,
    PlanInspection,
    PublishChecklist,
    RaisePunchItem,
    RecordInspectionResult,
    ReinspectInspection,
    ReopenPunchItem,
    RetireChecklist,
    ReviseChecklist,
    ScheduleInspection,
    VerifyInspection,
    VerifyPunchItem,
    VoidPunchItem,
)
from tl_mod_quality.guards import not_cancelled, not_retired, not_void
from tl_mod_quality.handlers.checklist import (
    handle_create_checklist,
    handle_edit_checklist,
    handle_publish_checklist,
    handle_retire_checklist,
    handle_revise_checklist,
)
from tl_mod_quality.handlers.inspection import (
    handle_cancel_inspection,
    handle_plan_inspection,
    handle_record_inspection_result,
    handle_reinspect_inspection,
    handle_schedule_inspection,
    handle_verify_inspection,
)
from tl_mod_quality.handlers.punch import (
    handle_clear_punch_item,
    handle_edit_punch_item,
    handle_raise_punch_item,
    handle_reopen_punch_item,
    handle_verify_punch_item,
    handle_void_punch_item,
)
from tl_mod_quality.names import (
    CHECKLIST,
    CHECKLIST_EDIT,
    CHECKLIST_PUBLISH,
    CLEAR,
    EDIT,
    INSPECTION,
    INSPECTION_CANCEL,
    INSPECTION_PLAN,
    INSPECTION_RECORD,
    INSPECTION_VERIFY,
    PUNCH_ITEM,
    RAISE,
    RECORD_TYPES,
    REOPEN,
    VERIFY,
    VOID_WORD,
)
from tl_mod_quality.projectors import (
    ChecklistProjector,
    InspectionProjector,
    PunchItemProjector,
)


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

#: Checklists and inspections (P2-INSP S2). The word of each is a ``quality.checklist.*`` or
#: ``quality.inspection.*`` word of ``schema/settings/access-words.yaml``.
INSP_COMMANDS: tuple[PunchCommand, ...] = (
    PunchCommand(CreateChecklist, handle_create_checklist, CHECKLIST_EDIT),
    PunchCommand(EditChecklist, handle_edit_checklist, CHECKLIST_EDIT),
    PunchCommand(PublishChecklist, handle_publish_checklist, CHECKLIST_PUBLISH),
    PunchCommand(RetireChecklist, handle_retire_checklist, CHECKLIST_PUBLISH),
    PunchCommand(ReviseChecklist, handle_revise_checklist, CHECKLIST_PUBLISH),
    PunchCommand(PlanInspection, handle_plan_inspection, INSPECTION_PLAN),
    PunchCommand(ScheduleInspection, handle_schedule_inspection, INSPECTION_PLAN),
    PunchCommand(RecordInspectionResult, handle_record_inspection_result, INSPECTION_RECORD),
    PunchCommand(VerifyInspection, handle_verify_inspection, INSPECTION_VERIFY),
    PunchCommand(ReinspectInspection, handle_reinspect_inspection, INSPECTION_PLAN),
    PunchCommand(CancelInspection, handle_cancel_inspection, INSPECTION_CANCEL),
)

#: The table the ``commands`` hook names: every command of the module.
QUALITY_COMMANDS: tuple[PunchCommand, ...] = PUNCH_COMMANDS + INSP_COMMANDS

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A punch item takes property values, links, files and the life of its links until it is Void
#: (``guards.not_void``); a checklist and an inspection take the same until Retired or Cancelled
#: (``guards.not_retired``, ``guards.not_cancelled``). Their fields and state change only through
#: the module's commands: not ``UpdateRecord``, ``VoidRecord`` or ``TransitionWorkflow``
#: (ADR-0010 addendum 1).
PUNCH_GENERIC_COMMANDS = frozenset({"SetPsetValues", "AddLink", "AttachFile"}) | LINK_LIFE

#: What an agent may propose (ADR-0014 section 8, ADR-0027): a new punch item and a planned
#: inspection. Accepting runs ``RaisePunchItem`` or ``PlanInspection`` as the accepting person, who
#: needs ``quality.punch.raise`` or ``quality.inspection.plan`` (both ``user`` words). The other
#: commands are in ``tests/tools/proposable_exclusions.toml`` with the reason.
PROPOSABLE = (
    ProposableCommand("propose_punch_item", RaisePunchItem, handle_raise_punch_item, "user"),
    ProposableCommand("propose_inspection", PlanInspection, handle_plan_inspection, "user"),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [PunchItemProjector(), ChecklistProjector(), InspectionProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            PUNCH_ITEM: PUNCH_GENERIC_COMMANDS,
            CHECKLIST: PUNCH_GENERIC_COMMANDS,
            INSPECTION: PUNCH_GENERIC_COMMANDS,
        },
        generic_guards={
            **{(PUNCH_ITEM, c): not_void for c in PUNCH_GENERIC_COMMANDS},
            **{(CHECKLIST, c): not_retired for c in PUNCH_GENERIC_COMMANDS},
            **{(INSPECTION, c): not_cancelled for c in PUNCH_GENERIC_COMMANDS},
        },
        proposable=PROPOSABLE,
        actions={PUNCH_ITEM: punch_actions},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in QUALITY_COMMANDS},
        commands="tl_mod_quality.module:QUALITY_COMMANDS",
        read_routers=("tl_api.routes.punch:router", "tl_api.routes.insp:router"),
        tools=(
            "tl_mcp.punch_tools:register_punch_tools",
            "tl_mcp.insp_tools:register_insp_tools",
        ),
        cli_groups=("tl_cli.punch:app", "tl_cli.insp:app", "tl_cli.checklist:app"),
        # a walkdown raises items offline; each is numbered when it syncs (offline classes)
        offline_drafts={
            PUNCH_ITEM: frozenset({"RaisePunchItem"}),
            INSPECTION: frozenset({"RecordInspectionResult"}),
        },
    )
