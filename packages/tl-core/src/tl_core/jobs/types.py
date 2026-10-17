"""Shared types of the job queue (ADR-0014): states, claims, and the unit-of-work factory shape."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from tl_core.uow import UnitOfWork

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"
STATES = (QUEUED, RUNNING, DONE, FAILED, CANCELLED)

DEFAULT_LEASE_S = 300.0
DEFAULT_MAX_ATTEMPTS = 3
#: A failed attempt waits this long times its number before the next one (30 s, 60 s, ...).
RETRY_BASE_S = 30.0
#: The stored error text is cut to this many characters.
MAX_ERROR = 500

Clock = Callable[[], datetime]

#: ``done``: this call completed the job. ``already``: it was completed by this same attempt
#: before (a retry of the completion). ``lost``: the claim was taken over or the job is no longer
#: running; the caller must write nothing.
Completion = Literal["done", "already", "lost"]
#: ``retry``: queued again. ``final``: no attempt left or a permanent failure. ``already``: the
#: failure of this attempt was recorded before. ``lost``: the claim is no longer this caller's.
FailOutcome = Literal["retry", "final", "already", "lost"]


class UowFactory(Protocol):
    """Opens an entered unit of work: one transaction, committed on normal exit."""

    def __call__(self, *, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


def iso_z(moment: datetime) -> str:
    """ISO-8601 UTC with microseconds and a ``Z`` suffix; sorts correctly as text."""
    if moment.tzinfo is None:
        raise ValueError("iso_z requires a timezone-aware datetime")
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


@dataclass(frozen=True)
class Claim:
    """A job leased to one worker for one attempt."""

    job_id: str
    kind: str
    scope: str
    attempt: int
    max_attempts: int
    owner: str
    lease_until: str


@dataclass(frozen=True)
class Expired:
    """A running job whose lease ran out with no attempt left. It was failed for good."""

    job_id: str
    kind: str
    scope: str
    attempt: int
    max_attempts: int


@dataclass(frozen=True)
class QueueRow:
    job_id: str
    kind: str
    scope: str
    state: str
    priority: int
    attempt: int
    max_attempts: int
    run_after: str
    lease_owner: str | None
    lease_until: str | None
    enqueued_at: str
    started_at: str | None
    finished_at: str | None
    last_error: str | None
