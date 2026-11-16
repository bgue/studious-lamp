"""The ten permit commands (P2-PTW S2).

The API builds one ``POST /commands/<Name>`` route per row of ``module.COMMANDS``. Every model is
``extra="forbid"``: the requester, approver, issuer and closer are the actor of the command, never
a field. A state command takes ``expected_version`` (``None`` skips the check) and names the permit
by id in ``permit``. Every text has a length and is cleaned with ``tl_core.text``.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_DESCRIPTION = 1000
MAX_AREA = 64
MAX_LOCATION = 120
MAX_HOLDER = 120
MAX_NOTE = 300
MAX_ID = 40
MAX_TICKS = 20
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"

PermitType = Literal[
    "hot_work", "confined_space", "work_at_height", "excavation", "isolation", "general"
]


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


def _description(value: str) -> str:
    """A text that may span lines (tab and newline allowed), nothing else of the C0 set."""
    clean_text(value.replace("\n", "").replace("\t", ""))
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _day(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("a date must be a calendar date, YYYY-MM-DD") from None
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class RequestPermit(_Strict):
    """Ask for a permit (state Requested, key ``P123-PTW-0001``). ``requested_by`` is the actor.
    ``for_record_id`` names the record the work belongs to; the window is two calendar days."""

    permit_type: PermitType
    for_record_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    area: str = Field(min_length=1, max_length=MAX_AREA)
    location_text: str = Field(min_length=1, max_length=MAX_LOCATION)
    work_description: str = Field(min_length=1, max_length=MAX_DESCRIPTION)
    holder: str = Field(min_length=1, max_length=MAX_HOLDER)
    needed_from: str = Field(pattern=DATE_PATTERN)
    needed_until: str = Field(pattern=DATE_PATTERN)

    @field_validator("area", "location_text", "holder")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return _text(value)

    @field_validator("work_description")
    @classmethod
    def _detail(cls, value: str) -> str:
        return _description(value)

    @field_validator("needed_from", "needed_until")
    @classmethod
    def _dates(cls, value: str) -> str:
        return _day(value)

    @model_validator(mode="after")
    def _window(self) -> RequestPermit:
        if self.needed_until < self.needed_from:
            raise ValueError("needed_until is before needed_from")
        return self


class _OnPermit(_Strict):
    permit: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class _WithReason(_OnPermit):
    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class ApprovePermit(_OnPermit):
    """Requested to Approved, by a controller who is not the requester."""


class RejectPermit(_WithReason):
    """Requested to Rejected, with a reason, by a controller who is not the requester."""


class IssuePermit(_OnPermit):
    """Approved to Active. ``precautions`` are the ids ticked from the type's list."""

    precautions: list[str] = Field(default_factory=list[str], max_length=MAX_TICKS)

    @field_validator("precautions")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item or len(item) > 64:
                raise ValueError("a precaution id is 1 to 64 characters")
            _text(item)
        if len(set(value)) != len(value):
            raise ValueError("a precaution is ticked once")
        return value


class RevalidatePermit(_OnPermit):
    """Active or Lapsed: ``valid_until`` moves to the end of the next shift."""


class SuspendPermit(_WithReason):
    """Active or Lapsed to Suspended (stop work), by anyone holding the word."""


class ResumePermit(_OnPermit):
    """Suspended to Active; the issue guards run again."""


class HandBackPermit(_OnPermit):
    """Active, Lapsed or Suspended to Handed back, with the note that the site is safe."""

    handback_note: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("handback_note")
    @classmethod
    def _note(cls, value: str) -> str:
        return _text(value)


class ClosePermit(_OnPermit):
    """Handed back to Closed."""


class CancelPermit(_WithReason):
    """Requested or Approved to Cancelled, with a reason."""


__all__ = [
    "ApprovePermit",
    "CancelPermit",
    "ClosePermit",
    "HandBackPermit",
    "IssuePermit",
    "RejectPermit",
    "RequestPermit",
    "ResumePermit",
    "RevalidatePermit",
    "SuspendPermit",
]
