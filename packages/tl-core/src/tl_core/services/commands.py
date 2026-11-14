"""Command models: validated input to the record command handlers (brief 5.1)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tl_core.intent import Intent
from tl_core.ledger import Event

_SCOPE_PATTERN = re.compile(r"(?:company|project:[A-Za-z0-9_.-]+)")
#: An idempotency key: printable ASCII without a space, 1 to 128 characters (P2-X1).
KEY_PATTERN = re.compile(r"[\x21-\x7e]{1,128}")
KEY_REFUSED = "idempotency key must be 1 to 128 printable ASCII characters"


def contains_nul(value: Any) -> bool:
    """Whether a string, or any string inside a list, tuple, dict or model, holds a NUL.

    A NUL cannot be stored in a Postgres text parameter: the driver raises an error that carries the
    statement and its values. A command refuses it first, as a validation error.
    """
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if "\x00" in item:
                return True
        elif isinstance(item, dict):
            mapping = cast("dict[Any, Any]", item)
            stack.extend(mapping.keys())
            stack.extend(mapping.values())
        elif isinstance(item, list | tuple | set | frozenset):
            stack.extend(cast("Iterable[Any]", item))
        elif isinstance(item, BaseModel):
            stack.extend(item.__dict__.values())
    return False


class Command(BaseModel):
    # a refused idempotency key must not come back in the error text (P2-X1)
    model_config = ConfigDict(hide_input_in_errors=True)

    actor: str
    source: str
    scope: str  # must match ^(company|project:[A-Za-z0-9_.-]+)$
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None  # ASCII 1..128; the API door and `propose` honour it
    intent: Intent | None = None

    @field_validator("idempotency_key")
    @classmethod
    def check_idempotency_key(cls, value: str | None) -> str | None:
        if value is not None and KEY_PATTERN.fullmatch(value) is None:
            raise ValueError(KEY_REFUSED)  # never the key itself
        return value

    @field_validator("scope")
    @classmethod
    def check_scope(cls, value: str) -> str:
        if _SCOPE_PATTERN.fullmatch(value) is None:
            raise ValueError(f"scope must be 'company' or 'project:<id>', got {value!r}")
        return value

    @model_validator(mode="after")
    def _no_nul(self) -> Command:
        """No text of any command may hold a NUL (it would crash a Postgres write)."""
        if contains_nul(self.__dict__):
            raise ValueError("text must not contain NUL characters")
        return self


class CreateRecord(Command):
    record_type: str  # Phase 0: only "core.Record"
    title: str = Field(min_length=1)
    description: str | None = None
    key: str | None = None  # None: the numbering service allocates one (brief 8)
    psets: dict[str, Any] = {}
    # Values for pattern fields other than {project} and {type}, e.g. {"discipline": "PIP"}.
    numbering: dict[str, str] = {}


class UpdateRecord(Command):
    stream_id: str
    expected_version: int
    changes: dict[str, Any]  # new values by field name


class VoidRecord(Command):
    stream_id: str
    expected_version: int
    reason: str  # non-blank after strip

    @field_validator("reason")
    @classmethod
    def check_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class CommandResult(BaseModel):
    stream_id: str
    key: str | None
    version: int
    events: list[Event]
