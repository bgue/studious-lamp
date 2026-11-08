"""What the requisitions module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``requisitions`` in this package's ``pyproject.toml``
names ``spec``. The module registers its record types and projectors; it has ten commands
(``REQUISITIONS_COMMANDS`` is the ten commands of P2-I4A S2). The four requisition kinds are
``draft_only`` offline and the work order is ``none`` (``schema/modules/requisitions``); the
drafts a foreman captures are listed with the commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tl_core.modules import ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from tl_mod_requisitions import MODULE
from tl_mod_requisitions.actions import requisitions_actions
from tl_mod_requisitions.commands import (
    ApproveRequisition,
    AssignWorkOrder,
    CancelRequisition,
    CloseWorkOrder,
    CompleteWorkOrder,
    EditRequisition,
    RaiseRequisition,
    RejectRequisition,
    ScheduleWorkOrder,
    StartWorkOrder,
)
from tl_mod_requisitions.guards import not_final
from tl_mod_requisitions.handlers.requisitions import (
    handle_approve_requisition,
    handle_cancel_requisition,
    handle_edit_requisition,
    handle_raise_requisition,
    handle_reject_requisition,
)
from tl_mod_requisitions.handlers.work_orders import (
    handle_assign_work_order,
    handle_close_work_order,
    handle_complete_work_order,
    handle_schedule_work_order,
    handle_start_work_order,
)
from tl_mod_requisitions.names import (
    APPROVE,
    ASSIGN,
    CANCEL,
    CLOSE,
    COMPLETE,
    EDIT,
    RAISE,
    RECORD_TYPES,
    REJECT,
    REQUISITION_TYPES,
    SCHEDULE,
    START,
    WORK_ORDER,
)
from tl_mod_requisitions.projectors import RequisitionProjector, WorkOrderProjector


@dataclass(frozen=True)
class RequisitionCommand:
    """A command, its handler and its fine access word (the API reads ``model`` and ``access``)."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str


#: The word the API table (``tl_api.commands``) reads for the module's row type.
ApiCommand = RequisitionCommand

REQUISITIONS_COMMANDS: tuple[RequisitionCommand, ...] = (
    RequisitionCommand(RaiseRequisition, handle_raise_requisition, RAISE),
    RequisitionCommand(EditRequisition, handle_edit_requisition, EDIT),
    RequisitionCommand(ApproveRequisition, handle_approve_requisition, APPROVE),
    RequisitionCommand(RejectRequisition, handle_reject_requisition, REJECT),
    RequisitionCommand(CancelRequisition, handle_cancel_requisition, CANCEL),
    RequisitionCommand(ScheduleWorkOrder, handle_schedule_work_order, SCHEDULE),
    RequisitionCommand(AssignWorkOrder, handle_assign_work_order, ASSIGN),
    RequisitionCommand(StartWorkOrder, handle_start_work_order, START),
    RequisitionCommand(CompleteWorkOrder, handle_complete_work_order, COMPLETE),
    RequisitionCommand(CloseWorkOrder, handle_close_work_order, CLOSE),
)

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A requisition takes property values (a crane lift's property set), links, files and the life of
#: its links until it is Closed, Rejected or Cancelled (``guards.not_final``). Its fields and state
#: change only through the module's commands. A work order takes links and their life.
REQUISITION_GENERIC_COMMANDS = (
    frozenset({"SetPsetValues", "AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
)
WORK_ORDER_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE

#: What an agent may propose (ADR-0014 section 8, ADR-0027): a new requisition. Accepting runs
#: ``RaiseRequisition`` as the accepting person, who needs ``requisitions.raise`` (a ``user``
#: word). Approve, reject, schedule and close are acts, and the field edits are the owner's:
#: ``tests/tools/proposable_exclusions.toml`` lists them with the reason.
PROPOSABLE = (
    ProposableCommand("propose_requisition", RaiseRequisition, handle_raise_requisition, "user"),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [RequisitionProjector(), WorkOrderProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        company_roles=False,
        generic_commands={
            **{t: REQUISITION_GENERIC_COMMANDS for t in REQUISITION_TYPES},
            WORK_ORDER: WORK_ORDER_GENERIC_COMMANDS,
        },
        generic_guards={
            **{(t, c): not_final for t in REQUISITION_TYPES for c in REQUISITION_GENERIC_COMMANDS},
            **{(WORK_ORDER, c): not_final for c in WORK_ORDER_GENERIC_COMMANDS},
        },
        proposable=PROPOSABLE,
        actions={record_type: requisitions_actions for record_type in RECORD_TYPES},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in REQUISITIONS_COMMANDS},
        # a foreman raises a requisition offline; it is numbered when it syncs (offline classes)
        offline_drafts={t: frozenset({"RaiseRequisition"}) for t in REQUISITION_TYPES},
    )


