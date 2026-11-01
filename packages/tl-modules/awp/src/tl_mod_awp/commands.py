"""The commands the awp module offers to the API (spec m3-wbs-cwp section 3; P2-I1).

The API builds one ``POST /commands/<Name>`` route per row of ``AWP_COMMANDS``. ``access`` is the
fine access word of ``schema/settings/access-words.yaml`` (``awp.wbs.configure`` and the rest); the
role table reads each as its table word (``read``, ``user``, ``controller``). An agent never changes
a record: its call is a proposal a person accepts, and a command is closed to agents until
``tl_core.auth.provider`` lists it.

This file holds the command models. Every text has a length and every list a bound before a handler
reads it; a rule that needs the ledger (depth, leaf-only, the sum of an allocation) is the
handler's, with a fixed message. S4 adds the package commands to ``AWP_COMMANDS``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.services.commands import Command, CommandResult
from tl_core.text import clean_optional_text, clean_text
from tl_core.uow import UnitOfWork

from tl_mod_awp.handlers.cwa import (
    handle_define_cwa,
    handle_retire_cwa,
    handle_revise_cwa,
)
from tl_mod_awp.handlers.path import (
    handle_define_path_of_construction,
    handle_move_cwa_in_path,
)
from tl_mod_awp.handlers.wbs import (
    handle_define_wbs_node,
    handle_map_wbs_to_cost_codes,
    handle_retire_wbs_node,
    handle_revise_wbs_node,
)
from tl_mod_awp.limits import (
    CODE_PATTERN,
    MAX_ALLOCATIONS,
    MAX_COST_CODE,
    MAX_ID,
    MAX_LOCATION,
    MAX_NOTE,
    MAX_PATH_STEPS,
    MAX_REASON,
    MAX_REASON_CODE,
    MAX_TITLE,
    REASON_CODE_PATTERN,
)


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class CostCodeLine(BaseModel):
    """One line of a node's cost code allocation: the cost code's code and a percent as text."""

    model_config = ConfigDict(extra="forbid")

    cost_code: str = Field(min_length=1, max_length=MAX_COST_CODE)
    percent: str = Field(min_length=1, max_length=12)

    @field_validator("cost_code")
    @classmethod
    def _code(cls, value: str) -> str:
        return clean_text(value)


class PathStepIn(BaseModel):
    """One place of a new path: the area's code and, optionally, a reason."""

    model_config = ConfigDict(extra="forbid")

    cwa_code: str = Field(pattern=CODE_PATTERN)
    reason_code: str | None = Field(default=None, pattern=REASON_CODE_PATTERN)


class DefineWbsNode(_Strict):
    """Create a WBS node under a parent (or at the root) at a place among its siblings."""

    code: str = Field(pattern=CODE_PATTERN)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    parent_code: str | None = Field(default=None, pattern=CODE_PATTERN)
    position: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _text(value)


class ReviseWbsNode(_Strict):
    """Rename, move or re-order a node. A field that is left out stays; ``parent_code`` sent as
    ``null`` moves the node to the root."""

    node: str = Field(min_length=1, max_length=MAX_ID)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    parent_code: str | None = Field(default=None, pattern=CODE_PATTERN)
    position: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


class RetireWbsNode(_Strict):
    node: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class MapWbsToCostCodes(_Strict):
    """Replace the cost code allocation of a leaf node (1 to 20 lines summing to 100.00)."""

    node: str = Field(min_length=1, max_length=MAX_ID)
    allocations: list[CostCodeLine] = Field(min_length=1, max_length=MAX_ALLOCATIONS)


class DefinePathOfConstruction(_Strict):
    """Define the project's path of construction (version 1)."""

    steps: list[PathStepIn] = Field(min_length=1, max_length=MAX_PATH_STEPS)


class MoveCwaInPath(_Strict):
    """Move one area to a place in the path; the result is the next version."""

    cwa_code: str = Field(pattern=CODE_PATTERN)
    to_position: int = Field(ge=1, le=MAX_PATH_STEPS)
    reason_code: str = Field(pattern=REASON_CODE_PATTERN, max_length=MAX_REASON_CODE)
    note: str | None = Field(default=None, max_length=MAX_NOTE)
    expected_version: int = Field(ge=1)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class DefineCwa(_Strict):
    code: str = Field(pattern=CODE_PATTERN)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    location_text: str | None = Field(default=None, max_length=MAX_LOCATION)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _text(value)

    @field_validator("location_text")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReviseCwa(_Strict):
    """Rename an area or change where it is. ``location_text`` sent as ``null`` clears it."""

    cwa: str = Field(min_length=1, max_length=MAX_ID)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    location_text: str | None = Field(default=None, max_length=MAX_LOCATION)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("location_text")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class RetireCwa(_Strict):
    cwa: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


@dataclass(frozen=True)
class AwpCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: str  # a fine word of schema/settings/access-words.yaml


AWP_COMMANDS: tuple[AwpCommand, ...] = (
    AwpCommand(DefineWbsNode, handle_define_wbs_node, "awp.wbs.configure"),
    AwpCommand(ReviseWbsNode, handle_revise_wbs_node, "awp.wbs.configure"),
    AwpCommand(RetireWbsNode, handle_retire_wbs_node, "awp.wbs.configure"),
    AwpCommand(MapWbsToCostCodes, handle_map_wbs_to_cost_codes, "awp.wbs.configure"),
    AwpCommand(DefinePathOfConstruction, handle_define_path_of_construction, "awp.path.configure"),
    AwpCommand(MoveCwaInPath, handle_move_cwa_in_path, "awp.path.configure"),
    AwpCommand(DefineCwa, handle_define_cwa, "awp.cwa.edit"),
    AwpCommand(ReviseCwa, handle_revise_cwa, "awp.cwa.edit"),
    AwpCommand(RetireCwa, handle_retire_cwa, "awp.wbs.configure"),
)
