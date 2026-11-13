"""The punch commands (P2-PUNCH S2): raise, edit, clear, verify, reopen, void.

The API builds one ``POST /commands/<Name>`` route per row of ``PUNCH_COMMANDS`` (``module.py``).
``access`` is the fine access word of ``schema/settings/access-words.yaml``; the role table reads
each as its table word. Every model is ``extra="forbid"``: ``raised_by`` is never a field, it is the
actor of the command (a body that names it is refused as an unknown field). A state command takes
``expected_version`` (``None`` skips the check). Every text has a length and is cleaned with
``tl_core.text`` before a handler reads it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_SUBJECT = 200
MAX_DESCRIPTION = 1000
MAX_SHORT = 64
MAX_ASSIGNEE = 120
MAX_NOTE = 300
MAX_ID = 40
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"

Category = Literal["A", "B", "C"]
#: The fields an edit may name.
EDIT_FIELDS = ("subject", "description", "area", "system", "due_on", "assignee", "category")


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


def _description(value: str | None) -> str | None:
    """A text that may span lines (tab and newline allowed), nothing else of the C0 set."""
    if value is None:
        return None
    clean_text(value.replace("\n", "").replace("\t", ""))
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _day(value: str | None) -> str | None:
    if value is not None:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("a date must be a calendar date, YYYY-MM-DD") from None
    return value


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("a time must carry its time zone")
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class RaisePunchItem(_Strict):
    """Raise a punch item (state Open, key ``P123-PUN-0001``). ``raised_by`` is the actor.
    ``from_record_id`` names the record it was raised from (a ``raised_against`` link)."""

    subject: str = Field(min_length=1, max_length=MAX_SUBJECT)
    description: str | None = Field(default=None, min_length=1, max_length=MAX_DESCRIPTION)
    area: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    system: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    due_on: str | None = Field(default=None, pattern=DATE_PATTERN)
    assignee: str | None = Field(default=None, min_length=1, max_length=MAX_ASSIGNEE)
    category: Category = "B"
    from_record_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)

    @field_validator("subject", "area", "system", "assignee")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("description")
    @classmethod
    def _detail(cls, value: str | None) -> str | None:
        return _description(value)

    @field_validator("due_on")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return _day(value)


class _OnItem(_Strict):
    punch_item: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class EditPunchItem(_OnItem):
    """Change fields of an Open punch item; at least one is named. A field left out stays; an
    optional field sent as ``null`` clears (the subject and the category cannot be cleared)."""

    subject: str | None = Field(default=None, min_length=1, max_length=MAX_SUBJECT)
    description: str | None = Field(default=None, min_length=1, max_length=MAX_DESCRIPTION)
    area: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    system: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    due_on: str | None = Field(default=None, pattern=DATE_PATTERN)
    assignee: str | None = Field(default=None, min_length=1, max_length=MAX_ASSIGNEE)
    category: Category | None = None

    @field_validator("subject", "area", "system", "assignee")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("description")
    @classmethod
    def _detail(cls, value: str | None) -> str | None:
        return _description(value)

    @field_validator("due_on")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return _day(value)

    @model_validator(mode="after")
    def _something(self) -> EditPunchItem:
        sent = [f for f in EDIT_FIELDS if f in self.model_fields_set]
        if not sent:
            raise ValueError("name at least one field to change")
        for required in ("subject", "category"):
            if required in sent and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be cleared")
        return self


class ClearPunchItem(_OnItem):
    """Open to Cleared. ``at``: when the work was done (not in the future, not before the day the
    item was raised), else now. The actor is recorded as ``cleared_by``."""

    note: str = Field(min_length=1, max_length=MAX_NOTE)
    at: datetime | None = None

    @field_validator("note")
    @classmethod
    def _note(cls, value: str) -> str:
        return _text(value)

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class VerifyPunchItem(_OnItem):
    """Cleared to Verified, by someone other than the person who cleared it. ``at`` as for clear."""

    at: datetime | None = None

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class ReopenPunchItem(_OnItem):
    """Cleared or Verified back to Open; the cleared and verified columns reset."""

    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class VoidPunchItem(_OnItem):
    """Open or Cleared to Void, the final state."""

    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


__all__ = [
    "ClearPunchItem",
    "EditPunchItem",
    "RaisePunchItem",
    "ReopenPunchItem",
    "VerifyPunchItem",
    "VoidPunchItem",
]
