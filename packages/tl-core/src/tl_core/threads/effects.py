"""The two things a dispatch does that are not a command of the typed table (FANOUT D10).

``/remind`` queues a ``thread.reminder`` job and ``/summarise`` posts a deterministic summary. Both
are *effects*: a planned item with a ``command_type`` of their own, validated and run by the
dispatch engine, so they show in the preview like a command and run in the same unit of work.
Neither is reachable from a client: the effect models are not in the API command table, and the
engine runs them only for a plan the planner built and the caller confirmed.

A reminder's time is kept as typed (``+2h``) in the planned item and resolved when it runs, so the
preview token does not change from one second to the next. A date without a time means 00:00 UTC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from tl_core.jobs.queue import JobQueue
from tl_core.ledger import Event
from tl_core.threads.config import reminders_max_pending
from tl_core.threads.contract import (
    MAX_MENTIONS,
    REMIND_MAX_DAYS,
    SUMMARY_MAX_CHARS,
)
from tl_core.threads.messages import post_message
from tl_core.threads.visibility import ThreadRecord
from tl_core.uow import UnitOfWork

EFFECT_REMINDER = "ThreadReminder"
EFFECT_SUMMARY = "ThreadSummary"
REMINDER_JOB_KIND = "thread.reminder"
REMINDER_MAX_ATTEMPTS = 3

_COUNT = re.compile(r"\+(\d{1,7})([mhdw])")
_SECONDS = {"m": 60, "h": 3_600, "d": 86_400, "w": 604_800}


class ThreadReminder(BaseModel):
    """``when`` as typed after ``/remind``; ``who`` actor strings; ``text`` what to say."""

    model_config = ConfigDict(extra="forbid")

    when: str = Field(max_length=32)
    who: list[str] = Field(default_factory=list[str], max_length=MAX_MENTIONS)
    text: str | None = Field(default=None, max_length=1_000)


class ThreadSummary(BaseModel):
    """The text of a deterministic summary (``/summarise``)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=SUMMARY_MAX_CHARS)


#: Effect command types and the model that validates each. Access is ``user`` for both: they change
#: nothing but the thread and the job queue.
EFFECT_MODELS: dict[str, type[BaseModel]] = {
    EFFECT_REMINDER: ThreadReminder,
    EFFECT_SUMMARY: ThreadSummary,
}


@dataclass(frozen=True)
class StepResult:
    """What one planned item did: the stream it touched and whether it created a record."""

    command_type: str
    stream_id: str
    key: str | None
    version: int
    created_record: bool = False
    events: list[Event] = field(default_factory=list[Event])


_PENDING_BY_SQL = text(
    "SELECT "
    "COALESCE(SUM(CASE WHEN m.record_id = :record_id THEN 1 ELSE 0 END), 0) AS in_thread, "
    "COALESCE(SUM(CASE WHEN m.author = :author THEN 1 ELSE 0 END), 0) AS by_author "
    "FROM job_queue j JOIN cur_thread_message m ON m.message_id = j.job_id "
    "WHERE j.kind = :kind AND j.state IN ('queued', 'running')"
)


def _check_reminder_caps(uow: UnitOfWork, record: ThreadRecord, actor: str) -> None:
    """Refuse a reminder when the thread, or the person, already has the allowed number waiting."""
    cap = reminders_max_pending(uow.conn(), record.scope)
    row = (
        uow.conn()
        .execute(
            _PENDING_BY_SQL, {"kind": REMINDER_JOB_KIND, "record_id": record.id, "author": actor}
        )
        .one()
    )
    if int(row.in_thread) >= cap:
        raise ValueError(f"this thread already has {cap} reminders waiting")
    if int(row.by_author) >= cap:
        raise ValueError(f"you already have {cap} reminders waiting")


def resolve_when(when: str, now: datetime) -> datetime | None:
    """The instant ``when`` stands for, or ``None`` when it is not a time (the parser checked it).

    ``+<n>m|h|d|w`` counts from ``now``; ``YYYY-MM-DD`` is 00:00 UTC of that day;
    ``YYYY-MM-DDTHH:MM`` is that minute, UTC.
    """
    found = _COUNT.fullmatch(when)
    if found is not None:
        return now + timedelta(seconds=int(found.group(1)) * _SECONDS[found.group(2)])
    try:
        if "T" in when:
            return datetime.strptime(when, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        day = date.fromisoformat(when)
    except ValueError:
        return None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def reminder_problem(when: str, now: datetime) -> str | None:
    """Why ``when`` cannot be a reminder time now (past, or too far ahead), else ``None``."""
    moment = resolve_when(when, now)
    if moment is None:
        return "that is not a time"
    if moment <= now:
        return "that time has passed"
    if moment > now + timedelta(days=REMIND_MAX_DAYS):
        return f"a reminder is at most {REMIND_MAX_DAYS} days ahead"
    return None


def validate_effect(command_type: str, data: dict[str, Any]) -> str | None:
    """A short problem text when ``data`` is not a valid effect, else ``None``. No values echoed."""
    model = EFFECT_MODELS.get(command_type)
    if model is None:
        return "unknown effect"
    try:
        model.model_validate(data)
    except ValidationError as exc:
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:300]
    return None


def run_effect(
    uow: UnitOfWork,
    *,
    record: ThreadRecord,
    actor: str,
    command_type: str,
    data: dict[str, Any],
    message_id: str,
    now: datetime,
) -> StepResult:
    """Run one effect inside the dispatch's unit of work."""
    if command_type == EFFECT_REMINDER:
        reminder = ThreadReminder.model_validate(data)
        moment = resolve_when(reminder.when, now)
        if moment is None or moment <= now:
            raise ValueError("the reminder time is not in the future")
        _check_reminder_caps(uow, record, actor)
        JobQueue().enqueue(
            uow.conn(),
            job_id=message_id,
            kind=REMINDER_JOB_KIND,
            scope=record.scope,
            now=now,
            max_attempts=REMINDER_MAX_ATTEMPTS,
            run_after=moment,
        )
        return StepResult(command_type, message_id, None, 1)
    if command_type == EFFECT_SUMMARY:
        summary = ThreadSummary.model_validate(data)
        posted = post_message(
            uow,
            record=record,
            actor=actor,
            source=f"thread:{record.id}",
            body=summary.text,
            kind="summary",
            correlation_id=f"dispatch:{message_id}",
        )
        return StepResult(
            command_type, posted.stream_id, posted.key, posted.version, events=posted.events
        )
    raise ValueError(f"unknown effect {command_type!r}")
