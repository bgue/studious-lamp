"""The commands the requisitions module offers (P2-I4A S2; design ``requisitions-and-scaffold.md``).

The API builds one ``POST /commands/<Name>`` route per row of ``REQUISITIONS_COMMANDS`` (in
``module.py``). ``access`` is the fine access word of ``schema/settings/access-words.yaml``; the role
table reads each as its table word. An agent never changes a record: its call is a proposal a person
accepts (``module.PROPOSABLE``), and a command is closed to agents until ``tl_core.auth.provider``
lists it.

Every text has a length and every list a bound before a handler reads it. Every edit of an existing
record takes ``expected_version`` (ADR-0027). ``requester`` is never a field: it is the actor of the
command (F4), and a body that names it is refused as an unknown field.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_SUBJECT = 200
MAX_LOCATION = 200
MAX_ID = 40
MAX_CRAFT = 64
MAX_SHIFT = 32
MAX_REQUIREMENTS = 500
MAX_PURPOSE = 300
MAX_REASON = 300
MAX_ASSIGNEE = 120
MAX_LINES = 200
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
QTY_PATTERN = r"^(0|[1-9][0-9]{0,9})(\.[0-9]{1,4})?$"
DIMENSION_PATTERN = r"^(0|[1-9][0-9]{0,5})(\.[0-9]{1,3})?$"
HOURS_PATTERN = r"^((0|[1-9][0-9]{0,6})\.[0-9]|10000000\.0)$"
TYPE_CODE_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"

Priority = Literal["low", "normal", "high", "urgent"]


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


def _multiline(value: str | None) -> str | None:
    """A text that may span lines (tab and newline allowed), with nothing else of the C0 set."""
    if value is None:
        return None
    clean_text(value.replace("\n", "").replace("\t", ""))
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("a time must carry its time zone")
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class _Body(BaseModel):
    """What every kind of requisition carries."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=MAX_SUBJECT)
    need_by: str | None = Field(default=None, pattern=DATE_PATTERN)
    location_text: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION)
    priority: Priority = "normal"

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return _text(value)

    @field_validator("location_text")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


class RequisitionLine(BaseModel):
    """One line of a material requisition: a project item, a quantity and its unit."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1, max_length=MAX_ID)
    qty: str = Field(pattern=QTY_PATTERN)
    uom: str = Field(min_length=1, max_length=8)
    cost_code_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)

    @field_validator("uom")
    @classmethod
    def _uom(cls, value: str) -> str:
        return _text(value)


class LaborBody(_Body):
    kind: Literal["labor"]
    craft: str = Field(min_length=1, max_length=MAX_CRAFT)
    classification: str | None = Field(default=None, min_length=1, max_length=MAX_CRAFT)
    headcount: int = Field(ge=1, le=500)
    start_date: str = Field(pattern=DATE_PATTERN)
    end_date: str = Field(pattern=DATE_PATTERN)
    shift: str | None = Field(default=None, min_length=1, max_length=MAX_SHIFT)
    requirements: str | None = Field(default=None, min_length=1, max_length=MAX_REQUIREMENTS)

    @field_validator("craft", "classification", "shift")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("requirements")
    @classmethod
    def _requirements(cls, value: str | None) -> str | None:
        return _multiline(value)


class MaterialBody(_Body):
    kind: Literal["material"]
    from_location_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    lines: list[RequisitionLine] = Field(min_length=1, max_length=MAX_LINES)


class GeneralBody(_Body):
    kind: Literal["general"]
    general_type: str = Field(pattern=TYPE_CODE_PATTERN)


class ScaffoldBody(_Body):
    kind: Literal["scaffold"]
    purpose: str = Field(min_length=1, max_length=MAX_PURPOSE)
    elevation: str | None = Field(default=None, min_length=1, max_length=32)
    gridline: str | None = Field(default=None, min_length=1, max_length=32)
    length_m: str | None = Field(default=None, pattern=DIMENSION_PATTERN)
    width_m: str | None = Field(default=None, pattern=DIMENSION_PATTERN)
    height_m: str | None = Field(default=None, pattern=DIMENSION_PATTERN)
    load_class: str | None = Field(default=None, min_length=1, max_length=32)
    duration_days: int = Field(ge=1, le=1000)

    @field_validator("elevation", "gridline", "load_class")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("purpose")
    @classmethod
    def _purpose(cls, value: str) -> str:
        return _multiline(value) or ""


#: ``kind`` selects the model.
RequisitionBody = Annotated[
    LaborBody | MaterialBody | GeneralBody | ScaffoldBody, Field(discriminator="kind")
]


class RaiseRequisition(_Strict):
    """Raise a requisition (state Requested, numbered per kind). The requester is the actor.
    ``for_record_id`` names the IWP or CWP it serves (a ``requires`` link from it);
    ``cost_code_id`` and ``activity_id`` are ``references`` links."""

    requisition: RequisitionBody
    for_record_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    cost_code_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    activity_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)


class EditRequisition(_Strict):
    """Change fields of a requisition while it is Requested. A field left out stays; the kind's own
    fields only (a craft on a material requisition is refused). Optional fields sent as ``null``
    clear."""

    requisition: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int = Field(ge=1)
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_SUBJECT)
    need_by: str | None = Field(default=None, pattern=DATE_PATTERN)
    location_text: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION)
    priority: Priority | None = None
    craft: str | None = Field(default=None, min_length=1, max_length=MAX_CRAFT)
    classification: str | None = Field(default=None, min_length=1, max_length=MAX_CRAFT)
    headcount: int | None = Field(default=None, ge=1, le=500)
    start_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    end_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    shift: str | None = Field(default=None, min_length=1, max_length=MAX_SHIFT)
    requirements: str | None = Field(default=None, min_length=1, max_length=MAX_REQUIREMENTS)
    from_location_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    lines: list[RequisitionLine] | None = Field(default=None, min_length=1, max_length=MAX_LINES)
    general_type: str | None = Field(default=None, pattern=TYPE_CODE_PATTERN)
    purpose: str | None = Field(default=None, min_length=1, max_length=MAX_PURPOSE)
    elevation: str | None = Field(default=None, min_length=1, max_length=32)
    gridline: str | None = Field(default=None, min_length=1, max_length=32)
    length_m: str | None = Field(default=None, pattern=DIMENSION_PATTERN)
    width_m: str | None = Field(default=None, pattern=DIMENSION_PATTERN)
    height_m: str | None = Field(default=None, pattern=DIMENSION_PATTERN)
    load_class: str | None = Field(default=None, min_length=1, max_length=32)
    duration_days: int | None = Field(default=None, ge=1, le=1000)

    @field_validator(
        "subject",
        "location_text",
        "craft",
        "classification",
        "shift",
        "elevation",
        "gridline",
        "load_class",
    )
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("requirements", "purpose")
    @classmethod
    def _multi(cls, value: str | None) -> str | None:
        return _multiline(value)


class ApproveRequisition(_Strict):
    """Requested to Approved; opens the work order. The requester may not approve their own."""

    requisition: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int = Field(ge=1)


class RejectRequisition(_Strict):
    requisition: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class CancelRequisition(_Strict):
    """Requested or Approved to Cancelled, by the requester or an approver; an Open work order is
    cancelled with it."""

    requisition: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class _OnWorkOrder(_Strict):
    work_order: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int = Field(ge=1)


class ScheduleWorkOrder(_OnWorkOrder):
    """Open to Scheduled; the requisition becomes Scheduled with it."""

    planned_start: str = Field(pattern=DATE_PATTERN)
    planned_finish: str = Field(pattern=DATE_PATTERN)
    hours_planned: str | None = Field(default=None, pattern=HOURS_PATTERN)


class AssignWorkOrder(_OnWorkOrder):
    """Set who does the work (a person or free text), while Open or Scheduled."""

    assigned_to: str = Field(min_length=1, max_length=MAX_ASSIGNEE)

    @field_validator("assigned_to")
    @classmethod
    def _assignee(cls, value: str) -> str:
        return _text(value)


class StartWorkOrder(_OnWorkOrder):
    """Scheduled to In progress. ``at``: when the work started (not in the future), else now."""

    at: datetime | None = None

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class CompleteWorkOrder(_OnWorkOrder):
    """In progress to Done. ``at``: when the work finished (not in the future), else now."""

    at: datetime | None = None
    hours_actual: str | None = Field(default=None, pattern=HOURS_PATTERN)

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class CloseWorkOrder(_OnWorkOrder):
    """Done to Closed; the requisition closes with it."""


__all__ = [
    "ApproveRequisition",
    "AssignWorkOrder",
    "CancelRequisition",
    "CloseWorkOrder",
    "CompleteWorkOrder",
    "EditRequisition",
    "GeneralBody",
    "LaborBody",
    "MaterialBody",
    "RaiseRequisition",
    "RejectRequisition",
    "RequisitionBody",
    "RequisitionLine",
    "ScaffoldBody",
    "ScheduleWorkOrder",
    "StartWorkOrder",
]
