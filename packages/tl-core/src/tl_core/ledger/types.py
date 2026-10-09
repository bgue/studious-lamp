"""Ledger value types and the Ledger Protocol (brief §5.1)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel


class NewEvent(BaseModel):
    """What a command handler emits. The ledger fills seq, stream_version, hashes, recorded_at."""

    event_type: str  # e.g. "Record.Created"
    schema_version: int = 1
    payload: dict[str, Any]
    effective_at: datetime | None = None  # defaults to recorded_at


class Event(BaseModel):
    """A stored event: NewEvent's fields (effective_at required) plus the ledger-assigned ones."""

    event_type: str
    schema_version: int = 1
    payload: dict[str, Any]
    seq: int
    event_id: str  # ULID
    stream_id: str
    stream_type: str
    stream_version: int
    scope: str  # "company" | "project:<id>"
    # "user:<id>" | "svc:<name>" | "agent:<id>" (+ on_behalf_of in payload)
    actor: str
    recorded_at: datetime
    effective_at: datetime
    correlation_id: str
    causation_id: str | None
    source: str
    prev_hash: str | None
    hash: str


class AppendResult(BaseModel):
    events: list[Event]
    new_version: int
    last_seq: int


class ConcurrencyError(Exception):
    """expected_version did not match the stream's current version."""


class Ledger(Protocol):
    def append(
        self,
        *,
        stream_id: str,
        stream_type: str,
        scope: str,
        expected_version: int,  # 0 for a new stream
        events: Sequence[NewEvent],
        actor: str,
        source: str,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> AppendResult: ...
    def read_stream(self, stream_id: str, *, from_version: int = 1) -> list[Event]: ...
    def read_after(
        self, seq: int, *, scope: str | None = None, limit: int = 1000
    ) -> list[Event]: ...
    def head_seq(self) -> int: ...
    def stream_version(self, stream_id: str) -> int: ...  # 0 if absent
