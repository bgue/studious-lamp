"""The punch commands (P2-PUNCH S2): raise, edit, clear, verify, reopen, void.

The API builds one ``POST /commands/<Name>`` route per row of ``PUNCH_COMMANDS`` (``module.py``).
``access`` is the fine access word of ``schema/settings/access-words.yaml``; the role table reads
each as its table word. Every model is ``extra="forbid"``: ``raised_by`` is never a field, it is the
actor of the command (a body that names it is refused as an unknown field). A state command takes
``expected_version`` (``None`` skips the check). Every text has a length and is cleaned with
``tl_core.text`` before a handler reads it.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

from tl_mod_quality.insp_rules import (
    MAX_ANSWER_TEXT,
    MAX_QUESTIONS,
)
from tl_mod_quality.insp_rules import (
    MAX_NOTE as MAX_ANSWER_NOTE,
)

MAX_SUBJECT = 200
MAX_DESCRIPTION = 1000
MAX_SHORT = 64
MAX_ASSIGNEE = 120
MAX_NOTE = 300
MAX_ID = 40
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"

MAX_TITLE = 200
MAX_CHECKLIST_JSON = 100_000
MAX_ANSWER_ID = 16
MAX_INSPECTION_NOTE = 1000

Category = Literal["A", "B", "C"]
Point = Literal["hold", "witness", "review", "surveillance"]
#: The fields an edit may name.
EDIT_FIELDS = ("subject", "description", "area", "system", "due_on", "assignee", "category")
#: The fields a checklist edit may name.
CHECKLIST_EDIT_FIELDS = ("title", "discipline", "questions")


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


# --- checklists and inspections (P2-INSP S2) -----------------------------------------------------


def _clean_strings(value: Any) -> None:
    """Refuse a control or direction character in any text of a nested list or dict."""
    if isinstance(value, str):
        clean_text(value.replace("\n", "").replace("\t", ""))
    elif isinstance(value, dict):
        for key, inner in value.items():
            _clean_strings(key)
            _clean_strings(inner)
    elif isinstance(value, list):
        for inner in value:
            _clean_strings(inner)


def _questions(value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """At most ``MAX_QUESTIONS`` questions of bounded size; their shape is checked on publish."""
    if value is None:
        return None
    _clean_strings(value)
    if len(json.dumps(value, ensure_ascii=False)) > MAX_CHECKLIST_JSON:
        raise ValueError("the question list is too large")
    return value


def _answers(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Answers of bounded size (the rules check them against the pinned questions)."""
    _clean_strings(value)
    for answer in value:
        question = answer.get("q")
        if isinstance(question, str) and len(question) > MAX_ANSWER_ID:
            raise ValueError("a question id is too long")
        for key in ("value", "note"):
            inner = answer.get(key)
            limit = MAX_ANSWER_NOTE if key == "note" else MAX_ANSWER_TEXT
            if isinstance(inner, str) and len(inner) > limit:
                raise ValueError(f"an answer {key} is too long")
        if len(answer) > 3:
            raise ValueError("an answer names a question, a value and a note")
    return [{"note": None, **answer} for answer in value]


class CreateChecklist(_Strict):
    """Create a checklist in Draft, version 1 (key ``P123-CHK-0001``). The question list is
    checked on publish; here it is only bounded."""

    title: str = Field(min_length=1, max_length=MAX_TITLE)
    discipline: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    questions: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_QUESTIONS)

    @field_validator("title", "discipline")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("questions")
    @classmethod
    def _bounded(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _questions(value) or []


class _OnChecklist(_Strict):
    checklist: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class EditChecklist(_OnChecklist):
    """Change fields of a Draft checklist; at least one is named. ``discipline`` sent as ``null``
    clears; the title and the questions cannot be cleared."""

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    discipline: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    questions: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_QUESTIONS)

    @field_validator("title", "discipline")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("questions")
    @classmethod
    def _bounded(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        return _questions(value)

    @model_validator(mode="after")
    def _something(self) -> EditChecklist:
        sent = [f for f in CHECKLIST_EDIT_FIELDS if f in self.model_fields_set]
        if not sent:
            raise ValueError("name at least one field to change")
        for required in ("title", "questions"):
            if required in sent and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be cleared")
        return self


class PublishChecklist(_OnChecklist):
    """Draft to Published; the question list must pass ``insp_rules.validate_questions``. A
    revision publishes and retires the version it supersedes in the same step."""


class RetireChecklist(_OnChecklist):
    """Draft or Published to Retired, the final state."""


class ReviseChecklist(_OnChecklist):
    """Copy a Published checklist as a new Draft, version n+1, ``supersedes_id`` the old one."""


class PlanInspection(_Strict):
    """Plan an inspection (state Planned, key ``P123-INS-0001``). ``subject_id`` is the record
    inspected and must be readable by the actor; ``for_iwp_id`` defaults to it. ``planned_by`` is
    the actor."""

    title: str = Field(min_length=1, max_length=MAX_TITLE)
    subject_id: str = Field(min_length=1, max_length=MAX_ID)
    point: Point
    for_iwp_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    area: str | None = Field(default=None, min_length=1, max_length=MAX_SHORT)
    planned_on: str | None = Field(default=None, pattern=DATE_PATTERN)

    @field_validator("title", "area")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("planned_on")
    @classmethod
    def _planned(cls, value: str | None) -> str | None:
        return _day(value)


class _OnInspection(_Strict):
    inspection: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class ScheduleInspection(_OnInspection):
    """Planned or Scheduled to Scheduled: a Published checklist (its version is pinned), a date
    and an inspector."""

    checklist: str = Field(min_length=1, max_length=MAX_ID)
    scheduled_for: str = Field(pattern=DATE_PATTERN)
    inspector: str = Field(min_length=1, max_length=MAX_ASSIGNEE)

    @field_validator("inspector")
    @classmethod
    def _inspector(cls, value: str) -> str:
        return _text(value)

    @field_validator("scheduled_for")
    @classmethod
    def _scheduled(cls, value: str) -> str:
        return _day(value) or value


class RecordInspectionResult(_OnInspection):
    """Scheduled to Done. The answers are checked against the pinned checklist; the result is
    computed (``insp_rules.result_of``), never sent. ``recorded_by`` is the actor. A reject or
    conditional result raises one punch item per failed question in the same step."""

    answers: list[dict[str, Any]] = Field(max_length=MAX_QUESTIONS)
    note: str | None = Field(default=None, min_length=1, max_length=MAX_INSPECTION_NOTE)
    at: datetime | None = None

    @field_validator("answers")
    @classmethod
    def _bounded(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _answers(value)

    @field_validator("note")
    @classmethod
    def _detail(cls, value: str | None) -> str | None:
        return _description(value)

    @field_validator("at")
    @classmethod
    def _at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class VerifyInspection(_OnInspection):
    """Done to Verified, by a controller who did not record it."""


class ReinspectInspection(_OnInspection):
    """Plan a new inspection that repeats a rejected or conditional one (``reinspection_of_id``);
    the old one is untouched."""

    planned_on: str | None = Field(default=None, pattern=DATE_PATTERN)

    @field_validator("planned_on")
    @classmethod
    def _planned(cls, value: str | None) -> str | None:
        return _day(value)


class CancelInspection(_OnInspection):
    """Planned or Scheduled to Cancelled, the final state."""

    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


__all__ = [
    "CancelInspection",
    "ClearPunchItem",
    "CreateChecklist",
    "EditChecklist",
    "EditPunchItem",
    "PlanInspection",
    "PublishChecklist",
    "RaisePunchItem",
    "RecordInspectionResult",
    "ReinspectInspection",
    "ReopenPunchItem",
    "RetireChecklist",
    "ReviseChecklist",
    "ScheduleInspection",
    "VerifyInspection",
    "VerifyPunchItem",
    "VoidPunchItem",
]
