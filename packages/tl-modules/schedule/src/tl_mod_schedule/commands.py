"""The commands the schedule module offers to the API (brief 11.1, 25.2; P1-I4, ADR-0015).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:

* ``controller``: an admin or a document controller (action ``control.command.<Name>``);
* ``user``: any signed-in person.

Defining a schedule, publishing a snapshot and voiding one are controlling acts: what the project's
current schedule is must not be changed by anyone who is signed in. Opening a snapshot, attaching
the XER file, queueing its build and linking a record to an activity are open to any signed-in
person: they create an unpublished, immutable snapshot, or a link, and change nothing a reader of
the current schedule sees. An agent never changes a record: its calls are proposals a person
accepts (``module.PROPOSABLE``), and a command is closed to agents until ``tl_core.auth.provider``
lists it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_schedule.handlers.activity import LinkActivity, handle_link_activity
from tl_mod_schedule.handlers.publish import (
    PublishScheduleSnapshot,
    handle_publish_schedule_snapshot,
)
from tl_mod_schedule.handlers.schedules import DefineSchedule, handle_define_schedule
from tl_mod_schedule.handlers.snapshots import (
    OpenScheduleSnapshot,
    StartScheduleSnapshot,
    VoidScheduleSnapshot,
    handle_open_schedule_snapshot,
    handle_start_schedule_snapshot,
    handle_void_schedule_snapshot,
)

Access = Literal["admin", "controller", "user"]  # a typo is a type error, not an open door


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    ApiCommand(DefineSchedule, handle_define_schedule, "controller"),
    ApiCommand(OpenScheduleSnapshot, handle_open_schedule_snapshot, "user"),
    ApiCommand(StartScheduleSnapshot, handle_start_schedule_snapshot, "user"),
    ApiCommand(PublishScheduleSnapshot, handle_publish_schedule_snapshot, "controller"),
    ApiCommand(VoidScheduleSnapshot, handle_void_schedule_snapshot, "controller"),
    ApiCommand(LinkActivity, handle_link_activity, "user"),
)
