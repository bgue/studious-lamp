"""``DefineSchedule``: register the series of XER snapshots of one P6 project.

A schedule has a code (its record key), a name, a type, an owner and, when an XER file holds more
than one project, the P6 project to read. Defining one is a controlling act of the document
controller (ADR-0015): it decides what the planning snapshots of a project are filed under.
"""

from __future__ import annotations

import re

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text
from tl_core.uow import UnitOfWork

from tl_mod_schedule.common import correlated, require_project
from tl_mod_schedule.errors import InvalidScheduleError
from tl_mod_schedule.limits import MAX_CODE, MAX_NAME, MAX_OWNER, MAX_P6_PROJECT
from tl_mod_schedule.names import SCHEDULE, SCHEDULE_DEFINED, SCHEDULE_TYPES

_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class DefineSchedule(Command):
    """Register a schedule of the project."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_CODE)
    name: str = Field(min_length=1, max_length=MAX_NAME)
    schedule_type: str = "current"
    owner: str | None = Field(default=None, max_length=MAX_OWNER)
    p6_project: str | None = Field(default=None, min_length=1, max_length=MAX_P6_PROJECT)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if _CODE.fullmatch(value) is None:
            raise ValueError(
                "a schedule code is letters, digits, '.', '_' and '-', starting with a letter "
                "or digit (it is part of the keys of its snapshots and activities)"
            )
        return value

    @field_validator("name", "owner", "p6_project")
    @classmethod
    def _plain(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def handle_define_schedule(uow: UnitOfWork, cmd: DefineSchedule) -> CommandResult:
    """Create the schedule record. Raises ``InvalidScheduleError`` for an unknown type."""
    require_project(cmd)
    cmd = correlated(cmd)
    if cmd.schedule_type not in SCHEDULE_TYPES:
        raise InvalidScheduleError(
            f"schedule_type must be one of {', '.join(SCHEDULE_TYPES)}, got {cmd.schedule_type!r}"
        )
    return create_module_record(
        uow,
        cmd,
        record_type=SCHEDULE,
        title=cmd.name,
        key=cmd.code,
        extra_events=[
            NewEvent(
                event_type=SCHEDULE_DEFINED,
                payload={
                    "code": cmd.code,
                    "schedule_type": cmd.schedule_type,
                    "owner": cmd.owner,
                    "p6_project": cmd.p6_project,
                },
            )
        ],
    )
