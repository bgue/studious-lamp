"""The ``thread.reminder`` job kind: a reminder falls due and is posted to the thread (brief 21.5).

``/remind`` queues a job whose id is the id of the dispatch message that asked for it (see
``tl_core.threads.effects``). Nothing else is stored: when the job runs, the kind reads that message
from the thread, parses its command line again and posts a ``reminder`` message as ``svc:threads``
naming who it is for. The job is the clock; the ledger is the memory.

* ``prepare`` (read-only) loads the message and parses it. A message that is gone or is not a
  ``/remind`` is a permanent failure (``message_missing``).
* ``run`` builds the text. Pure.
* ``settle`` posts the reminder in the settling transaction, which the queue guarantees runs at
  most once per job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from tl_core.confidentiality import use_viewer
from tl_core.integration.actor_access import viewer_of
from tl_core.jobs.runner import JobFailure
from tl_core.jobs.types import Claim
from tl_core.services.errors import RecordNotFoundError
from tl_core.threads.config import threads_enabled
from tl_core.threads.contract import ParsedDispatch, RemindArgs
from tl_core.threads.effects import REMINDER_JOB_KIND
from tl_core.threads.messages import post_message
from tl_core.threads.parser import CommandLineParser
from tl_core.threads.visibility import can_read_record, readable_record
from tl_core.uow import UnitOfWork

#: The actor of everything the server posts into a thread on its own.
THREAD_SERVICE_ACTOR = "svc:threads"

_MESSAGE_SQL = text(
    "SELECT message_id, record_id, scope, author, kind, body, retracted "
    "FROM cur_thread_message WHERE message_id = :message_id"
)


@dataclass(frozen=True)
class ReminderWork:
    """What ``prepare`` read: enough to write the reminder, nothing mutable."""

    message_id: str
    record_id: str
    scope: str
    setter: str
    who: tuple[str, ...]  # as typed, without the sigil
    note: str | None


def reminder_text(work: ReminderWork) -> str:
    """The body of the reminder: who set it, for whom, and what it says.

    ``Reminder from user:rgarcia for @lchen @kpatel: check the bevels``. With nobody named the
    reminder is for the person who set it.
    """
    text = f"Reminder from {work.setter}"
    if work.who:
        text += " for " + " ".join(f"@{name}" for name in work.who)
    if work.note:
        text += ": " + work.note
    return text


class ThreadReminderKind:
    """A :class:`~tl_core.jobs.runner.JobKind` for ``thread.reminder``."""

    kind = REMINDER_JOB_KIND

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        """Nothing is written when an attempt starts."""

    def prepare(self, uow: UnitOfWork, claim: Claim) -> ReminderWork:
        row = uow.conn().execute(_MESSAGE_SQL, {"message_id": claim.job_id}).first()
        if row is None or row.kind != "dispatch" or bool(row.retracted):
            raise JobFailure("message_missing", "the /remind message is gone", retryable=False)
        parsed = CommandLineParser().parse(str(row.body))
        if not isinstance(parsed, ParsedDispatch) or not isinstance(parsed.args, RemindArgs):
            raise JobFailure("message_missing", "the message is not a /remind", retryable=False)
        return ReminderWork(
            message_id=str(row.message_id),
            record_id=str(row.record_id),
            scope=str(row.scope),
            setter=str(row.author),
            who=tuple(parsed.args.who),
            note=parsed.args.text,
        )

    def run(self, work: ReminderWork) -> str:
        return reminder_text(work)

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Any) -> None:
        body: str = outcome
        row = uow.conn().execute(_MESSAGE_SQL, {"message_id": claim.job_id}).first()
        if row is None:
            raise JobFailure("message_missing", "the /remind message is gone", retryable=False)
        record_id, setter = str(row.record_id), str(row.author)
        # A reminder is posted by the thread service, which reads internal records only, for a
        # setter who must still be able to read the record: a record that is restricted or
        # privileged, or that became so after the reminder was set, ends it with a code that says
        # why (P1-I7 review; the runbook lists it). Nothing is posted and nothing is retried.
        try:
            record = readable_record(uow, record_id, actor=THREAD_SERVICE_ACTOR)
        except RecordNotFoundError:
            record = None
        if record is None or not can_read_record(uow, record_id, setter):
            raise JobFailure(
                "record_not_readable",
                "the record is not readable by the reminder's setter and the thread service",
                retryable=False,
            )
        if record.voided or not threads_enabled(uow.conn(), record.scope, record.record_type):
            # The record is void, or threads are off now: nothing is posted, and it is not retried.
            raise JobFailure(
                "thread_closed", "the thread is off or its record is void", retryable=False
            )
        # The note's #KEY tags are resolved as the person who set the reminder, not as the job
        # runner (which reads everything): a key the setter cannot read is no reference.
        with use_viewer(viewer_of(uow.conn(), setter)):
            post_message(
                uow,
                record=record,
                actor=THREAD_SERVICE_ACTOR,
                source=f"thread:{record.id}",
                body=body,
                kind="reminder",
                correlation_id=f"dispatch:{claim.job_id}",
                check_enabled=False,
            )

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        """A failed reminder leaves no event; the queue row keeps the code and the text."""

    def expired(self, uow: UnitOfWork, item: Any) -> None:
        """A reminder whose lease ran out for good leaves no event either."""


__all__ = ["ReminderWork", "ThreadReminderKind", "reminder_text"]
