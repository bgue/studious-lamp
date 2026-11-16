"""The scan code commands (P2-QR S2): issue, revoke, rotate.

Every model is ``extra="forbid"``; ``issued_by`` is the actor, never a field. A command never
carries a code: it names a record (``target_id``) or a code's register id (``code_id``).
Every text is cleaned with ``tl_core.text``.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_LABEL = 40
MAX_REASON = 300
MAX_ID = 40

Size = Literal["tag", "card", "sheet"]


def _text(value: str) -> str:
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


class _Strict(Command):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class IssueScanCode(_Strict):
    """Issue a scan code for a record. The code is returned to the service caller once."""

    target_id: str = Field(min_length=1, max_length=MAX_ID)
    label_text: str | None = Field(default=None, min_length=1, max_length=MAX_LABEL)
    size: Size = "tag"
    expires_on: date | None = None

    @field_validator("label_text")
    @classmethod
    def _label(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)


class RevokeScanCode(_Strict):
    """Revoke a scan code by its register id (never the code)."""

    code_id: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)


class RotateScanCode(_Strict):
    """Revoke a scan code and issue a new one for the same record, label, size and expiry."""

    code_id: str = Field(min_length=1, max_length=MAX_ID)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _text(value)
