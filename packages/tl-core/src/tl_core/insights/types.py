"""Models of the insights reads (ADR-0028). Activity models are added by their own piece."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from tl_core.readiness.types import RecordRef

CheckSeverity = Literal["blocking", "warning"]


class RecordFacts(BaseModel):
    """What a check source is told about the record it reads for."""

    record_id: str
    record_type: str
    key: str
    scope: str


class CheckFinding(BaseModel):
    """One thing that needs attention on a record, shaped like a readiness ``CheckResult``.

    A finding is a fact read from the record's own sources; it is never labelled a suggestion.
    """

    source: str
    subject_id: str
    state: str  # a word: blocked, pending, unknown, open, missing, overdue, short
    text: str
    since: str | None = None  # ISO date or time, or None
    severity: CheckSeverity
    resolve_via: list[RecordRef] = Field(default_factory=list[RecordRef])
