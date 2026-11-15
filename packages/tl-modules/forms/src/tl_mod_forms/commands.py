"""The forms commands (P2-FORMS S3): templates (draft, edit, publish, revise, retire), submissions
(save a draft, discard, submit) and review (accept, return, void).

``FORMS_COMMANDS`` (``module.py``) holds one row per model. ``access`` is the fine access word of
``schema/settings/access-words.yaml``. Every model is ``extra="forbid"``: the author of a submission
is never a field, it is the actor of the command. A command that changes a record takes
``expected_version`` (``None`` skips the check). Texts are cleaned with ``tl_core.text``. A list of
answers or fields is bounded here so a hostile body costs a bounded amount of work; what the rules
say about its content is the handler's (``tl_core.forms.rules``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core.forms.types import MAX_FIELDS
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_TITLE = 200
MAX_NOTE = 300
MAX_ID = 40
MAX_TYPE = 64
MAX_ANSWERS = 2 * MAX_FIELDS
MAX_FIELD_LIST = 2 * MAX_FIELDS
MAX_ACCEPTS = 5

AnswerClass = Literal["internal", "restricted", "privileged"]
EDIT_FIELDS = ("title", "fields", "answer_class", "intake", "purpose", "accepts_as")


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


def _clean_tree(value: Any) -> None:
    """Every text inside a field list is one clean line (a template holds no control character)."""
    if isinstance(value, str):
        clean_text(value)
    elif isinstance(value, dict):
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            clean_text(str(key))  # pyright: ignore[reportUnknownArgumentType]
            _clean_tree(item)
    elif isinstance(value, list):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            _clean_tree(item)


def _field_list(value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if value is not None:
        _clean_tree(value)
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


# --- templates ---------------------------------------------------------------------------------


class DraftFormTemplate(_Strict):
    """Make a template as a Draft (company scope, key ``TPL-0001``). The field list must be clean
    (``validate_questions``): an incomplete template is not stored."""

    title: str = Field(min_length=1, max_length=MAX_TITLE)
    format_version: Literal[1, 2] = 2
    fields: list[dict[str, Any]] = Field(max_length=MAX_FIELD_LIST)
    bound_record_type: str | None = Field(default=None, min_length=1, max_length=MAX_TYPE)
    answer_class: AnswerClass | None = None
    intake: Literal["public"] | None = None
    purpose: Literal["request", "sign_on"] | None = None
    accepts_as: list[str] | None = Field(default=None, max_length=MAX_ACCEPTS)

    @field_validator("title", "bound_record_type")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("fields")
    @classmethod
    def _fields(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _field_list(value) or []

    @field_validator("accepts_as")
    @classmethod
    def _accepts(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            for name in value:
                _text(name)
        return value


class _OnTemplate(_Strict):
    template_id: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class EditFormTemplate(_OnTemplate):
    """Change fields of a Draft template; at least one is named. A field left out stays; an optional
    field sent as ``null`` clears (the title and the field list cannot be cleared)."""

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    fields: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_FIELD_LIST)
    answer_class: AnswerClass | None = None
    intake: Literal["public"] | None = None
    purpose: Literal["request", "sign_on"] | None = None
    accepts_as: list[str] | None = Field(default=None, max_length=MAX_ACCEPTS)

    @field_validator("title")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("fields")
    @classmethod
    def _fields(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        return _field_list(value)

    @field_validator("accepts_as")
    @classmethod
    def _accepts(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            for name in value:
                _text(name)
        return value

    @model_validator(mode="after")
    def _something(self) -> EditFormTemplate:
        sent = [f for f in EDIT_FIELDS if f in self.model_fields_set]
        if not sent:
            raise ValueError("name at least one field to change")
        for required in ("title", "fields"):
            if required in sent and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be cleared")
        return self


class PublishFormTemplate(_OnTemplate):
    """Draft to Published: the questions are checked again, the content hash is fixed."""


class ReviseFormTemplate(_OnTemplate):
    """A Published or Retired template to a new Draft, version n+1, same fields and flags."""


class RetireFormTemplate(_OnTemplate):
    """A Published or Draft template to Retired, the final state."""


# --- submissions -------------------------------------------------------------------------------


class _Fill(_Strict):
    """What a save and a submit carry: the whole state of the draft. ``template_id`` starts a form
    (no ``draft_id``); ``draft_id`` continues one, whose template is the one it was started with."""

    template_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    draft_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    subject_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    answers: list[dict[str, Any]] = Field(max_length=MAX_ANSWERS)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _one_of(self) -> _Fill:
        if (self.template_id is None) == (self.draft_id is None):
            raise ValueError("name the template to start a form or the draft to continue, not both")
        return self


class SaveFormDraft(_Fill):
    """Save a draft: answers may be incomplete (``partial``). The first save makes the record with
    no number; ``draft_id`` saves again. ``subject_id`` is the record the form is about."""


class SubmitForm(_Fill):
    """Submit a form: answers are complete. Takes the number (``P123-FRM-0001``) at submit; a
    resubmit of a returned form keeps it."""


class _OnSubmission(_Strict):
    submission_id: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class DiscardFormDraft(_OnSubmission):
    """Discard a draft of the actor's own (state Draft); it never takes a number."""


class AcceptFormSubmission(_OnSubmission):
    """Submitted to Accepted, by someone other than the person who filled the form."""

    note: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


class ReturnFormSubmission(_OnSubmission):
    """Submitted to Returned, by someone other than the person who filled the form."""

    note: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str) -> str:
        return _text(value)


class VoidFormSubmission(_OnSubmission):
    """Submitted, Accepted or Returned to Voided, the final state."""

    reason: str = Field(min_length=1, max_length=MAX_NOTE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


__all__ = [
    "AcceptFormSubmission",
    "DiscardFormDraft",
    "DraftFormTemplate",
    "EditFormTemplate",
    "PublishFormTemplate",
    "RetireFormTemplate",
    "ReturnFormSubmission",
    "ReviseFormTemplate",
    "SaveFormDraft",
    "SubmitForm",
    "VoidFormSubmission",
]
