"""The commands the cost module offers to the API (brief 11.1, 25.2; P1-I4, ADR-0015).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:
``admin`` (action ``admin.command.<Name>``) or ``user`` (any signed-in person). Importing a cost
snapshot is the admin's: the figures are money, and Phase 1 has no cost role (a follow-up in
ADR-0015). Reading the plan is open (the CLI preview). An agent never changes a record: its calls
are proposals a person accepts, and a command is closed to agents until ``tl_core.auth.provider``
lists it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_cost.handlers.snapshots import ImportCostSnapshot, handle_import_cost_snapshot

Access = Literal["admin", "controller", "user"]  # a typo is a type error, not an open door


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    ApiCommand(ImportCostSnapshot, handle_import_cost_snapshot, "admin"),
)
