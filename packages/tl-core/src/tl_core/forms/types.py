"""Forms engine contract (ADR-0031; P2-FORMS S1).

Frozen once merged: change only by orchestrator decision. Imports no web, CLI, MCP, TUI or module
code.

A form source is a plugin found through the entry-point group FORM_SOURCE_ENTRY_POINT; each entry
point names a zero-argument callable that returns an object satisfying FormSource, one per record
type.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Connection

from tl_core.confidentiality import Viewer

FORM_SOURCE_ENTRY_POINT = "throughline.form_sources"
MAX_SOURCES = 32
FORMAT_1, FORMAT_2 = 1, 2
MAX_FIELDS = 60
MAX_FIELD_TEXT = 200
MAX_CHOICES = 8
MAX_SECTION = 64
MAX_HELP = 300
MAX_ANSWER_TEXT = 1000
MAX_NOTE = 300
MAX_PHOTOS = 10
MAX_CONDITION_DEPTH = 3
INTAKE_MAX_FIELDS = 8
INTAKE_TEXT_MAX = 280
INTAKE_MAX_ACCEPTS = 5
KINDS_1 = ("yes_no_na", "number", "text", "choice")
KINDS_2 = KINDS_1 + ("multi", "date", "photo")
KEYS_1 = ("id", "text", "kind", "required", "unit", "min", "max", "choices", "fails_when")
KEYS_2 = KEYS_1 + ("section", "help", "visible_when")
RESERVED_CLAIM_IDS = ("claim_name", "claim_company", "claim_phone")
INTAKE_PURPOSES = ("request", "sign_on")

MAX_FIXED_ARGS_BYTES = 4 * 1024
MAX_PREFILL_BYTES = 64 * 1024

_HASH = re.compile(r"^[0-9a-f]{64}$")


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return -1


class TemplateRef(BaseModel):
    """Which stored template version a form was built from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: str  # record type that stores the template ("forms.Template", ...)
    source_id: str
    version: int = Field(ge=1)
    fmt: Literal[1, 2]
    content_hash: str  # 64 lower hex

    @field_validator("content_hash")
    @classmethod
    def _hash(cls, v: str) -> str:
        if not _HASH.fullmatch(v):
            raise ValueError("content_hash must be 64 lower-case hex characters")
        return v


class FormBinding(BaseModel):
    """What a record offers to fill in, and the command that takes the answers."""

    model_config = ConfigDict(extra="forbid")

    record_type: str
    key: str
    template: TemplateRef | None = None
    available: bool
    reason: str | None = None  # a fixed word; set only when available is false
    command: str | None = None
    fixed_args: dict[str, Any] = Field(default_factory=dict[str, Any])
    answers_arg: str | None = None
    expected_version: int | None = None
    prefill: list[dict[str, Any]] = Field(
        default_factory=list[dict[str, Any]]
    )  # answers {q, value, note}

    @model_validator(mode="after")
    def _coherent(self) -> FormBinding:
        if self.available:
            if self.template is None or not self.command or not self.answers_arg:
                raise ValueError("an available binding needs a template, a command and answers_arg")
            if self.reason is not None:
                raise ValueError("reason is set only when the binding is not available")
        if self.answers_arg is not None and self.answers_arg in self.fixed_args:
            raise ValueError("fixed_args must not carry the answers_arg key")
        size = _json_size(self.fixed_args)
        if size < 0 or size > MAX_FIXED_ARGS_BYTES:
            raise ValueError("fixed_args must serialise to JSON within 4 KB")
        if len(self.prefill) > MAX_FIELDS:
            raise ValueError(f"prefill holds at most {MAX_FIELDS} answers")
        size = _json_size(self.prefill)
        if size < 0 or size > MAX_PREFILL_BYTES:
            raise ValueError("prefill must serialise to JSON within 64 KB")
        return self


@runtime_checkable
class FormSource(Protocol):
    """A record type's form offer.

    ``binding`` is a pure read: it never writes and never opens the network. It answers ``None``
    for a record the viewer cannot see, for an unknown record, and for a record type with no form;
    it never raises for a bad or hidden record. ``available=False`` only for a record the viewer
    can already read.
    """

    record_type: str
    view_word: str

    def binding(
        self, conn: Connection, record_id: str, viewer: Viewer, now: datetime
    ) -> FormBinding | None: ...
