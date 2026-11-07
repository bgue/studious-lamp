"""The commands the awp module offers to the API (spec m3-wbs-cwp section 3; P2-I1).

The API builds one ``POST /commands/<Name>`` route per row of ``AWP_COMMANDS``. ``access`` is the
fine access word of ``schema/settings/access-words.yaml`` (``awp.wbs.configure`` and the rest); the
role table reads each as its table word (``read``, ``user``, ``controller``). An agent never changes
a record: its call is a proposal a person accepts, and a command is closed to agents until
``tl_core.auth.provider`` lists it.

This file holds the command models. Every text has a length and every list a bound before a handler
reads it; a rule that needs the ledger (depth, leaf-only, the sum of an allocation) is the
handler's, with a fixed message. The package commands (construction work packages and the owner's
engineering and procurement packages) are in the second half of ``AWP_COMMANDS``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tl_core.services.commands import Command, CommandResult
from tl_core.text import clean_optional_text, clean_text
from tl_core.uow import UnitOfWork

from tl_mod_awp.facts import MAX_SCOPE_IDS
from tl_mod_awp.fields import (
    check_period,
    parse_date,
    parse_estimated_hours,
    parse_hours,
    parse_quantity,
)
from tl_mod_awp.handlers.cwa import (
    handle_define_cwa,
    handle_retire_cwa,
    handle_revise_cwa,
)
from tl_mod_awp.handlers.cwp import (
    handle_allocate_cwp_to_wbs,
    handle_close_cwp,
    handle_complete_cwp,
    handle_create_cwp,
    handle_release_cwp,
    handle_reopen_cwp,
    handle_request_rollup,
    handle_return_cwp,
    handle_revise_cwp,
    handle_start_cwp_development,
    handle_start_cwp_execution,
    handle_void_cwp,
)
from tl_mod_awp.handlers.iwp import (
    handle_cancel_iwp,
    handle_create_iwp,
    handle_pin_iwp_document,
    handle_return_iwp_to_development,
    handle_send_iwp_to_constraint_check,
    handle_start_iwp_development,
)
from tl_mod_awp.handlers.packages import (
    handle_record_external_package,
    handle_update_external_package,
    handle_void_external_package,
)
from tl_mod_awp.handlers.path import (
    handle_define_path_of_construction,
    handle_move_cwa_in_path,
)
from tl_mod_awp.handlers.scope import (
    handle_add_iwp_scope,
    handle_create_scope_item,
    handle_remove_iwp_scope,
    handle_split_iwp,
)
from tl_mod_awp.handlers.wbs import (
    handle_define_wbs_node,
    handle_map_wbs_to_cost_codes,
    handle_reinstate_wbs_node,
    handle_retire_wbs_node,
    handle_revise_wbs_node,
)
from tl_mod_awp.limits import (
    ACTOR_PATTERN,
    CODE_PATTERN,
    DATE_PATTERN,
    MAX_ALLOCATIONS,
    MAX_BUDGET_TEXT,
    MAX_CONTRACTOR,
    MAX_COST_CODE,
    MAX_CREW,
    MAX_DESCRIPTION,
    MAX_FOREMAN,
    MAX_ID,
    MAX_LIST_CODE,
    MAX_LOCATION,
    MAX_NOTE,
    MAX_PACKAGE_NO,
    MAX_PATH_STEPS,
    MAX_PIN_CODE,
    MAX_QUANTITIES,
    MAX_QUANTITY_TEXT,
    MAX_REASON,
    MAX_REASON_CODE,
    MAX_SCOPE_PER_COMMAND,
    MAX_SOURCE_SYSTEM,
    MAX_SPLIT_GROUPS,
    MAX_STATUS_TEXT,
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


class ReinstateWbsNode(_Strict):
    node: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class MapWbsToCostCodes(_Strict):
    """Replace the cost code allocation of a leaf node: 1 to 20 lines summing to 100.00, or no
    line, which clears the allocation."""

    node: str = Field(min_length=1, max_length=MAX_ID)
    allocations: list[CostCodeLine] = Field(min_length=0, max_length=MAX_ALLOCATIONS)


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


class QuantityRow(BaseModel):
    """One quantity of a package: a commodity and a unit (codes of the lists ``Commodity`` and
    ``UnitOfMeasure``, checked by the handler) and the amount as text."""

    model_config = ConfigDict(extra="forbid")

    commodity: str = Field(min_length=1, max_length=MAX_LIST_CODE)
    qty: str = Field(min_length=1, max_length=MAX_QUANTITY_TEXT)
    uom: str = Field(min_length=1, max_length=MAX_LIST_CODE)

    @field_validator("commodity", "uom")
    @classmethod
    def _code(cls, value: str) -> str:
        return clean_text(value)

    @field_validator("qty")
    @classmethod
    def _qty(cls, value: str) -> str:
        return parse_quantity(value)


class WbsLine(BaseModel):
    """One line of a package's allocation to WBS nodes: the node's code and a percent as text."""

    model_config = ConfigDict(extra="forbid")

    wbs_code: str = Field(pattern=CODE_PATTERN)
    percent: str = Field(min_length=1, max_length=12)


def _date(value: str | None) -> str | None:
    return None if value is None else parse_date(value)


def _hours(value: str | None) -> str | None:
    return None if value is None else parse_hours(value)


class CreateCwp(_Strict):
    """Create a construction work package, numbered from the pattern per discipline."""

    discipline: str = Field(pattern=r"^[A-Za-z0-9]{1,16}$")
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    cwa_code: str = Field(pattern=CODE_PATTERN)
    planned_start: str | None = Field(default=None, pattern=DATE_PATTERN)
    planned_finish: str | None = Field(default=None, pattern=DATE_PATTERN)
    budget_hours: str | None = Field(default=None, min_length=1, max_length=MAX_BUDGET_TEXT)
    quantities: list[QuantityRow] | None = Field(default=None, max_length=MAX_QUANTITIES)
    contractor_text: str | None = Field(default=None, max_length=MAX_CONTRACTOR)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _text(value)

    @field_validator("planned_start", "planned_finish")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)

    @field_validator("budget_hours")
    @classmethod
    def _hours(cls, value: str | None) -> str | None:
        return _hours(value)

    @field_validator("contractor_text")
    @classmethod
    def _contractor(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @model_validator(mode="after")
    def _period(self) -> CreateCwp:
        check_period(self.planned_start, self.planned_finish)
        return self


class ReviseCwp(_Strict):
    """Change the fields of a package that is Planned or In development. A field that is left out
    stays; ``planned_start``, ``planned_finish``, ``budget_hours``, ``quantities`` and
    ``contractor_text`` sent as ``null`` are cleared. A title and an area are never cleared."""

    cwp: str = Field(min_length=1, max_length=MAX_ID)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    cwa_code: str | None = Field(default=None, pattern=CODE_PATTERN)
    planned_start: str | None = Field(default=None, pattern=DATE_PATTERN)
    planned_finish: str | None = Field(default=None, pattern=DATE_PATTERN)
    budget_hours: str | None = Field(default=None, min_length=1, max_length=MAX_BUDGET_TEXT)
    quantities: list[QuantityRow] | None = Field(default=None, max_length=MAX_QUANTITIES)
    contractor_text: str | None = Field(default=None, max_length=MAX_CONTRACTOR)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("planned_start", "planned_finish")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)

    @field_validator("budget_hours")
    @classmethod
    def _hours(cls, value: str | None) -> str | None:
        return _hours(value)

    @field_validator("contractor_text")
    @classmethod
    def _contractor(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @model_validator(mode="after")
    def _period(self) -> ReviseCwp:
        check_period(self.planned_start, self.planned_finish)
        return self


class AllocateCwpToWbs(_Strict):
    """Replace the allocation of a package to WBS leaf nodes (1 to 20 lines summing to 100.00)."""

    cwp: str = Field(min_length=1, max_length=MAX_ID)
    allocations: list[WbsLine] = Field(min_length=1, max_length=MAX_ALLOCATIONS)


class _OnCwp(_Strict):
    cwp: str = Field(min_length=1, max_length=MAX_ID)


class StartCwpDevelopment(_OnCwp):
    """Planned to In development."""


class StartCwpExecution(_OnCwp):
    """Released for IWP development to Executing."""


class CompleteCwp(_OnCwp):
    """Executing to Complete."""


class ReleaseCwp(_Strict):
    """In development to Released for IWP development, if the package meets the preconditions and
    is still at ``expected_version`` (the version the caller read)."""

    cwp: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int = Field(ge=1)


class ReturnCwp(_Strict):
    """Released for IWP development back to In development; the fields are open again."""

    cwp: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class CloseCwp(_OnCwp):
    """Complete to Closed."""


class ReopenCwp(ReturnCwp):
    """Complete back to Executing."""


class VoidCwp(_Strict):
    """Void a package that is not Closed."""

    id: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class VoidExternalPackage(VoidCwp):
    """Void an engineering or procurement package reference."""


class RecordExternalPackage(_Strict):
    """Record the owner's engineering (``ewp``) or procurement (``pwp``) package as a mirror."""

    package_type: Literal["ewp", "pwp"]
    package_no: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$", max_length=MAX_PACKAGE_NO
    )
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    status_text: str | None = Field(default=None, max_length=MAX_STATUS_TEXT)
    forecast_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    actual_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    constraint_source: bool
    source_system: str | None = Field(default=None, max_length=MAX_SOURCE_SYSTEM)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _text(value)

    @field_validator("status_text", "source_system")
    @classmethod
    def _words(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("forecast_date", "actual_date")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)


class UpdateExternalPackage(_Strict):
    """Change the status, dates or constraint flag of a package reference. A text or a date sent
    as ``null`` is cleared; a field that is left out stays."""

    id: str = Field(min_length=1, max_length=MAX_ID)
    status_text: str | None = Field(default=None, max_length=MAX_STATUS_TEXT)
    forecast_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    actual_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    constraint_source: bool | None = None

    @field_validator("status_text")
    @classmethod
    def _words(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("forecast_date", "actual_date")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)


def _iwp_hours(value: str | None) -> str | None:
    return None if value is None else parse_estimated_hours(value)


class CreateIwp(_Strict):
    """Create an interim work package, numbered from the pattern per discipline."""

    discipline: str = Field(pattern=r"^[A-Za-z0-9]{1,16}$")
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    cwp_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    planned_start: str | None = Field(default=None, pattern=DATE_PATTERN)
    planned_finish: str | None = Field(default=None, pattern=DATE_PATTERN)
    foreman: str | None = Field(default=None, pattern=ACTOR_PATTERN, max_length=MAX_FOREMAN)
    estimated_hours: str | None = Field(default=None, min_length=1, max_length=MAX_BUDGET_TEXT)
    crew_text: str | None = Field(default=None, max_length=MAX_CREW)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _text(value)

    @field_validator("planned_start", "planned_finish")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)

    @field_validator("estimated_hours")
    @classmethod
    def _hours(cls, value: str | None) -> str | None:
        return _iwp_hours(value)

    @field_validator("crew_text")
    @classmethod
    def _crew(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class CreateScopeItem(_Strict):
    """Create a scope item: a commodity, a quantity and the hours estimated for it."""

    commodity: str = Field(min_length=1, max_length=MAX_LIST_CODE)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION)
    qty: str = Field(min_length=1, max_length=MAX_QUANTITY_TEXT)
    uom: str = Field(min_length=1, max_length=MAX_LIST_CODE)
    est_hours: str = Field(min_length=1, max_length=MAX_BUDGET_TEXT)
    cwp_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)

    @field_validator("commodity", "uom")
    @classmethod
    def _codes(cls, value: str) -> str:
        return clean_text(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _text(value)

    @field_validator("qty")
    @classmethod
    def _qty(cls, value: str) -> str:
        return parse_quantity(value)

    @field_validator("est_hours")
    @classmethod
    def _hours(cls, value: str) -> str:
        return parse_estimated_hours(value)


def _scope_ids(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise ValueError("a record is listed twice")
    return value


class AddIwpScope(_Strict):
    """Add scope items or tags to an IWP (at most 200 in one command)."""

    iwp: str = Field(min_length=1, max_length=MAX_ID)
    items: list[Annotated[str, Field(min_length=1, max_length=MAX_ID)]] = Field(
        min_length=1, max_length=MAX_SCOPE_PER_COMMAND
    )

    @field_validator("items")
    @classmethod
    def _items(cls, value: list[str]) -> list[str]:
        return _scope_ids(value)


class RemoveIwpScope(AddIwpScope):
    """Remove records from the scope of an IWP."""


class PinIwpDocument(_Strict):
    """Pin a document revision (a revision code), or the current revision (floating), to an IWP."""

    iwp: str = Field(min_length=1, max_length=MAX_ID)
    document: str = Field(min_length=1, max_length=MAX_ID)
    pin: str | None = Field(default=None, min_length=1, max_length=MAX_PIN_CODE)

    @field_validator("pin")
    @classmethod
    def _pin(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value)


class _OnIwp(_Strict):
    iwp: str = Field(min_length=1, max_length=MAX_ID)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class StartIwpDevelopment(_OnIwp):
    """Draft to In development."""


class SendIwpToConstraintCheck(_OnIwp):
    """In development to Constraint check."""


class ReturnIwpToDevelopment(_OnIwp):
    """Constraint check back to In development."""


class SplitIwp(_Strict):
    """Split an IWP into two or more: ``by_hours`` cuts the scope in key order into the fewest
    groups each within the upper size bound; ``by_scope`` takes the groups given."""

    iwp: str = Field(min_length=1, max_length=MAX_ID)
    mode: Literal["by_hours", "by_scope"]
    groups: list[list[Annotated[str, Field(min_length=1, max_length=MAX_ID)]]] | None = Field(
        default=None, max_length=MAX_SPLIT_GROUPS
    )
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)

    @model_validator(mode="after")
    def _groups(self) -> SplitIwp:
        if (self.mode == "by_scope") != (self.groups is not None):
            raise ValueError("groups go with the mode by_scope and with no other")
        if self.groups is not None and sum(len(g) for g in self.groups) > MAX_SCOPE_IDS:
            raise ValueError("the groups hold more records than a package may")
        return self


class CancelIwp(_Strict):
    """Cancel an IWP that is not Closed, Split or Cancelled."""

    iwp: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class RequestRollup(_Strict):
    """Queue the budget rollup of the project (idempotent: one queued run at a time)."""


@dataclass(frozen=True)
class AwpCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: str  # a fine word of schema/settings/access-words.yaml


AWP_COMMANDS: tuple[AwpCommand, ...] = (
    AwpCommand(DefineWbsNode, handle_define_wbs_node, "awp.wbs.configure"),
    AwpCommand(ReviseWbsNode, handle_revise_wbs_node, "awp.wbs.configure"),
    AwpCommand(RetireWbsNode, handle_retire_wbs_node, "awp.wbs.configure"),
    AwpCommand(ReinstateWbsNode, handle_reinstate_wbs_node, "awp.wbs.configure"),
    AwpCommand(MapWbsToCostCodes, handle_map_wbs_to_cost_codes, "awp.wbs.configure"),
    AwpCommand(DefinePathOfConstruction, handle_define_path_of_construction, "awp.path.configure"),
    AwpCommand(MoveCwaInPath, handle_move_cwa_in_path, "awp.path.configure"),
    AwpCommand(DefineCwa, handle_define_cwa, "awp.cwa.edit"),
    AwpCommand(ReviseCwa, handle_revise_cwa, "awp.cwa.edit"),
    AwpCommand(RetireCwa, handle_retire_cwa, "awp.wbs.configure"),
    AwpCommand(CreateCwp, handle_create_cwp, "awp.cwp.edit"),
    AwpCommand(ReviseCwp, handle_revise_cwp, "awp.cwp.edit"),
    AwpCommand(AllocateCwpToWbs, handle_allocate_cwp_to_wbs, "awp.cwp.edit"),
    AwpCommand(StartCwpDevelopment, handle_start_cwp_development, "awp.cwp.edit"),
    AwpCommand(StartCwpExecution, handle_start_cwp_execution, "awp.cwp.edit"),
    AwpCommand(CompleteCwp, handle_complete_cwp, "awp.cwp.edit"),
    AwpCommand(ReleaseCwp, handle_release_cwp, "awp.cwp.release"),
    AwpCommand(ReturnCwp, handle_return_cwp, "awp.cwp.release"),
    AwpCommand(CloseCwp, handle_close_cwp, "awp.cwp.close"),
    AwpCommand(ReopenCwp, handle_reopen_cwp, "awp.cwp.close"),
    AwpCommand(VoidCwp, handle_void_cwp, "awp.void"),
    AwpCommand(RecordExternalPackage, handle_record_external_package, "awp.package.edit"),
    AwpCommand(UpdateExternalPackage, handle_update_external_package, "awp.package.edit"),
    AwpCommand(VoidExternalPackage, handle_void_external_package, "awp.void"),
    AwpCommand(RequestRollup, handle_request_rollup, "awp.cwp.edit"),
    AwpCommand(CreateIwp, handle_create_iwp, "awp.iwp.edit"),
    AwpCommand(CreateScopeItem, handle_create_scope_item, "awp.iwp.edit"),
    AwpCommand(AddIwpScope, handle_add_iwp_scope, "awp.iwp.edit"),
    AwpCommand(RemoveIwpScope, handle_remove_iwp_scope, "awp.iwp.edit"),
    AwpCommand(PinIwpDocument, handle_pin_iwp_document, "awp.iwp.edit"),
    AwpCommand(StartIwpDevelopment, handle_start_iwp_development, "awp.iwp.edit"),
    AwpCommand(SendIwpToConstraintCheck, handle_send_iwp_to_constraint_check, "awp.iwp.edit"),
    AwpCommand(ReturnIwpToDevelopment, handle_return_iwp_to_development, "awp.iwp.edit"),
    AwpCommand(SplitIwp, handle_split_iwp, "awp.iwp.edit"),
    AwpCommand(CancelIwp, handle_cancel_iwp, "awp.void"),
)
