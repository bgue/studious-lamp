"""Command models: validated input to the record command handlers (brief 5.1)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from tl_core.ledger import Event

_SCOPE_PATTERN = re.compile(r"(?:company|project:[A-Za-z0-9_.-]+)")


class Command(BaseModel):
    actor: str
    source: str
    scope: str  # must match ^(company|project:[A-Za-z0-9_.-]+)$
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None  # accepted and ignored in this increment

    @field_validator("scope")
    @classmethod
    def check_scope(cls, value: str) -> str:
        if _SCOPE_PATTERN.fullmatch(value) is None:
            raise ValueError(f"scope must be 'company' or 'project:<id>', got {value!r}")
        return value


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
