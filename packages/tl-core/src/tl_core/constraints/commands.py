"""Constraint commands and the names and limits they share (ADR-0024 decisions 2, 3, 6, 7).

``source_kind`` is the constraint's source (``source`` of a command is the caller's, as for
every command). A person's ``RaiseConstraint`` reaches the rules with no module, so only
``manual`` is accepted; the other four sources are the modules'. ``CONSTRAINT_COMMANDS`` lists
the four commands with the access word the registry reads (a core word: one rule for every
record type)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from pydantic import ConfigDict, Field, field_validator

from tl_core.services.commands import Command, CommandResult
from tl_core.text import clean_optional_text, clean_text
from tl_core.uow import UnitOfWork

RECORD_TYPE: Final = "core.Constraint"
WORKFLOW_ID: Final = "core.constraint"
EDIT_WORD: Final = "core.constraint.edit"
VIEW_WORD: Final = "core.constraint.view"
WAIVE_WORD: Final = "core.constraint.waive"
ACCESS_MODULE: Final = "core"  # the module name the role resolver is asked about

ST_OPEN: Final = "Open"
ST_ASSIGNED: Final = "Assigned"
ST_CLEARED: Final = "Cleared"
ST_WITHDRAWN: Final = "Withdrawn"

SOURCE_MANUAL: Final = "manual"
SOURCE_CHECK: Final = "check"
ALL_SOURCES: Final = (SOURCE_MANUAL, SOURCE_CHECK, "rule", "feed_hold", "thread_hold")
SEVERITIES: Final = ("blocking", "advisory")
CATEGORIES: Final = (
    "materials",
    "labour",
    "scaffold",
    "equipment",
    "permit",
    "engineering",
    "rfi",
    "predecessor",
    "other",
)
REF_TYPES: Final = (
    "purchase_order",
    "labour_requisition",
    "scaffold_requisition",
    "equipment",
    "permit",
    "other",
)

EV_RAISED: Final = "Constraint.Raised"
EV_ASSIGNED: Final = "Constraint.Assigned"
EV_CLEARED: Final = "Constraint.Cleared"
EV_WITHDRAWN: Final = "Constraint.Withdrawn"
EVENT_TYPES: Final = frozenset({EV_RAISED, EV_ASSIGNED, EV_CLEARED, EV_WITHDRAWN})

TABLE: Final = "cur_core_constraint"
MAX_ID: Final = 64
MAX_TEXT: Final = 500
MAX_REASON: Final = 300
MAX_CHECK_NAME: Final = 64
MAX_REF_TEXT: Final = 60
PHASE_PATTERN: Final = r"^[a-z][a-z0-9_]{0,31}$"
HASH_PATTERN: Final = r"^[0-9a-f]{64}$"
ACTOR_PATTERN: Final = r"^user:.{1,59}$"
#: A date ``YYYY-MM-DD`` or a UTC timestamp ``YYYY-MM-DDTHH:MM:SSZ`` (world time, ADR-0024 d4).
WORLD_TIME_PATTERN: Final = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)?$"


def _text(value: str) -> str:
    """A text with something in it and no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class RaiseConstraint(_Strict):
    """Raise a constraint on a record the caller can see. A person raises ``manual`` only."""

    subject: str = Field(min_length=1, max_length=MAX_ID)
    phase: str = Field(pattern=PHASE_PATTERN)
    severity: Literal["blocking", "advisory"]
    category: Literal[
        "materials",
        "labour",
        "scaffold",
        "equipment",
        "permit",
        "engineering",
        "rfi",
        "predecessor",
        "other",
    ]
    owner: str | None = Field(default=None, pattern=ACTOR_PATTERN)
    description: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    source_kind: Literal["manual", "check", "rule", "feed_hold", "thread_hold"] = SOURCE_MANUAL
    check_name: str | None = Field(default=None, min_length=1, max_length=MAX_CHECK_NAME)
    facts_hash: str | None = Field(default=None, pattern=HASH_PATTERN)
    effective_at: str | None = Field(default=None, pattern=WORLD_TIME_PATTERN)
    due_at: str | None = Field(default=None, pattern=WORLD_TIME_PATTERN)
    target: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    target_ref_type: (
        Literal[
            "purchase_order",
            "labour_requisition",
            "scaffold_requisition",
            "equipment",
            "permit",
            "other",
        ]
        | None
    ) = None
    target_ref_text: str | None = Field(default=None, min_length=1, max_length=MAX_REF_TEXT)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("check_name", "target_ref_text")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class AssignConstraint(_Strict):
    """Give an open constraint to an owner."""

    constraint: str = Field(min_length=1, max_length=MAX_ID)
    owner: str = Field(pattern=ACTOR_PATTERN)


class ClearConstraint(_Strict):
    """Clear an open or assigned constraint; ``resolved_by`` names the record that resolved it."""

    constraint: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)
    cleared_at: str | None = Field(default=None, pattern=WORLD_TIME_PATTERN)
    resolved_by: str | None = Field(default=None, min_length=1, max_length=MAX_ID)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class WithdrawConstraint(_Strict):
    """Withdraw an open or assigned constraint (raised in error, or it no longer applies)."""

    constraint: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


@dataclass(frozen=True)
class ConstraintCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: str  # a fine word of schema/settings/access-words.yaml


def command_table() -> tuple[ConstraintCommand, ...]:
    """The four commands with their handlers and the word ``core.constraint.edit``."""
    from tl_core.constraints import handlers as h

    return (
        ConstraintCommand(RaiseConstraint, h.handle_raise_constraint, EDIT_WORD),
        ConstraintCommand(AssignConstraint, h.handle_assign_constraint, EDIT_WORD),
        ConstraintCommand(ClearConstraint, h.handle_clear_constraint, EDIT_WORD),
        ConstraintCommand(WithdrawConstraint, h.handle_withdraw_constraint, EDIT_WORD),
    )
