"""The scaffold commands (P2-I4B S1): register, design, erect, inspect, tag green, release, modify,
dismantle, remove.

``SCAFFOLD_COMMANDS`` (``module.py``) lists one row per command with its fine access word; the role
table reads each as its table word. Every model is ``extra="forbid"``: the inspector and every other
actor field is the actor of the command, never an input. A command on a scaffold takes
``expected_version`` (``None`` skips the check). Every text has a length and is cleaned with
``tl_core.text`` before a handler reads it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_TITLE = 200
MAX_LOCATION = 120
MAX_NOTE = 300
MAX_ID = 40

#: What an inspection that is not a pass may say; a pass is the green tag (``TagScaffoldGreen``).
FailedResult = Literal["conditional", "fail"]


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("a time must carry its time zone")
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class RegisterScaffold(_Strict):
    """Register a scaffold (state Requested, key ``P123-SCF-0001``) from an approved scaffold
    request: one scaffold per request; the request's elevation, gridline, load class and the record
    it serves are copied."""

    request_id: str = Field(min_length=1, max_length=MAX_ID)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    location_text: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION)

    @field_validator("title", "location_text")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


class _OnScaffold(_Strict):
    scaffold: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class _Noted(_OnScaffold):
    note: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


class DesignScaffold(_Noted):
    """Requested to Designed."""


class ErectScaffold(_Noted):
    """Designed to Erecting; the first inspection falls due one interval after today."""


class InspectScaffold(_Noted):
    """Record an inspection that is not a pass (conditional: tag yellow; fail: tag red). A fail on
    an Inspected or In Use scaffold also moves it to Modify. ``at``: when it was inspected (not in
    the future, not before the day the scaffold was registered), else now."""

    result: FailedResult
    at: datetime | None = None

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class TagScaffoldGreen(_Noted):
    """Record a passed inspection and tag the scaffold green; from Erecting or Modify it also moves
    to Inspected. Needs the controller word. ``at`` as for an inspection."""

    at: datetime | None = None

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class ReleaseScaffold(_OnScaffold):
    """Inspected to In Use; refused unless the tag is green."""


class ModifyScaffold(_OnScaffold):
    """Inspected or In Use to Modify; the tag stays until the next inspection."""

    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class DismantleScaffold(_OnScaffold):
    """Start taking the scaffold down (to Dismantle) once the dismantle check passes."""

    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class RemoveScaffold(_OnScaffold):
    """Dismantle to Removed, or Requested or Designed to Removed (the request is withdrawn)."""

    reason: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


__all__ = [
    "DesignScaffold",
    "DismantleScaffold",
    "ErectScaffold",
    "InspectScaffold",
    "ModifyScaffold",
    "RegisterScaffold",
    "ReleaseScaffold",
    "RemoveScaffold",
    "TagScaffoldGreen",
]
