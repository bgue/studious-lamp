"""The thread.reminder job kind: a /remind falls due and is posted to the thread."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import text
from thread_world import (
    TableRunner,
    everyone,
    make_person,
    make_record,
    planning_world,
)
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.queue import job_queue_for
from tl_core.jobs.runner import JobFailure, JobRunner
from tl_core.jobs.types import Claim
from tl_core.threads.dispatch import DispatchFromThread, handle_dispatch_from_thread
from tl_core.threads.planner import ThreadPlanner
from tl_core.threads.queries import read_thread
from tl_core.threads.reminders import (
    THREAD_SERVICE_ACTOR,
    ReminderWork,
    ThreadReminderKind,
    reminder_text,
)
from tl_core.util import utcnow

RUNNER = TableRunner()


@pytest.fixture(autouse=True)
def accounts(db: DbTarget) -> None:
    """The runner finds what an actor holds in its account, so the people who dispatch have one."""
    for name in ("rgarcia",):
        make_person(db, name)


@pytest.fixture(autouse=True)
def world() -> Iterator[None]:
    with planning_world():
        yield


def work(**kw: object) -> ReminderWork:
    base: dict[str, object] = {
        "message_id": "M",
        "record_id": "R",
        "scope": "project:P123",
        "setter": "user:rgarcia",
        "who": (),
        "note": None,
    }
    return ReminderWork(**{**base, **kw})  # type: ignore[arg-type]


def test_the_text_names_the_setter_the_people_and_the_note() -> None:
    assert reminder_text(work()) == "Reminder from user:rgarcia"
    assert reminder_text(work(who=("lchen",))) == "Reminder from user:rgarcia for @lchen"
    assert (
        reminder_text(work(who=("lchen", "kpatel"), note="check the bevels"))
        == "Reminder from user:rgarcia for @lchen @kpatel: check the bevels"
    )
    assert reminder_text(work(note="call")) == "Reminder from user:rgarcia: call"


def dispatch(db: DbTarget, rid: str, line: str) -> str:
    planner = ThreadPlanner(factory=lambda readonly=False: open_uow(db, readonly=readonly))
    with open_uow(db, readonly=True) as uow:
        found = planner.preview(
            uow, record_id=rid, text=line, actor="user:rgarcia", holds=everyone, runner=RUNNER
        )
    token = found.token  # type: ignore[union-attr]
    cmd = DispatchFromThread(
        actor="user:rgarcia",
        source="t",
        scope="project:P123",
        record_id=rid,
        text=line,
        token=token,
    )
    with open_uow(db) as uow:
        result = handle_dispatch_from_thread(uow, cmd, holds=everyone, runner=RUNNER)
    assert result.key
    return result.key


def runner_for(db: DbTarget, *, later: timedelta) -> JobRunner:
    with open_uow(db, readonly=True) as uow:
        queue = job_queue_for(uow.conn())
    return JobRunner(
        lambda readonly=False: open_uow(db, readonly=readonly),
        queue,
        [ThreadReminderKind()],
        clock=lambda: utcnow() + later,
    )


def test_a_reminder_that_is_due_is_posted_by_the_thread_service(db: DbTarget) -> None:
    make_person(db, "lchen")
    rid = make_record(db, "REC-1")
    dispatch(db, rid, "/remind +1h @lchen check the bevels")
    assert runner_for(db, later=timedelta(minutes=5)).run_until_idle() == []  # not yet due
    done = runner_for(db, later=timedelta(hours=2)).run_until_idle()
    assert [r.outcome for r in done] == ["done"]
    with open_uow(db, readonly=True) as uow:
        page = read_thread(uow, rid, actor="user:x")
        sources = (
            uow.conn()
            .execute(
                text(
                    "SELECT source, correlation_id FROM events "
                    "WHERE event_type = 'Thread.MessagePosted'"
                )
            )
            .all()
        )
    assert page.kinds == ["dispatch", "reminder"]
    last = page.messages[-1]
    assert last.author == THREAD_SERVICE_ACTOR
    assert last.body == "Reminder from user:rgarcia for @lchen: check the bevels"
    assert last.mentions == ["lchen"]
    assert sources[-1].source == f"thread:{rid}"
    assert sources[-1].correlation_id.startswith("dispatch:")
    assert runner_for(db, later=timedelta(hours=3)).run_until_idle() == []  # at most once


def test_a_reminder_for_nobody_is_for_the_person_who_set_it(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    dispatch(db, rid, "/remind +1d")
    runner_for(db, later=timedelta(days=2)).run_until_idle()
    with open_uow(db, readonly=True) as uow:
        assert (
            read_thread(uow, rid, actor="user:x").messages[-1].body == "Reminder from user:rgarcia"
        )


def test_a_job_whose_message_is_gone_or_not_a_remind_fails_for_good(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    linked = dispatch(db, rid, "/link REC-2")
    kind = ThreadReminderKind()
    for job_id in ("NOPE", linked):
        claim = Claim(job_id, "thread.reminder", "project:P123", 1, 3, "w", "2099-01-01T00:00:00Z")
        with open_uow(db, readonly=True) as uow, pytest.raises(JobFailure) as raised:
            kind.prepare(uow, claim)
        assert raised.value.code == "message_missing" and not raised.value.retryable


def test_a_plain_message_that_reads_like_a_remind_is_not_a_reminder(db: DbTarget) -> None:
    from tl_core.threads.messages import PostThreadMessage, handle_post_thread_message

    rid = make_record(db, "REC-1")
    with open_uow(db) as uow:
        plain = handle_post_thread_message(
            uow,
            PostThreadMessage(
                actor="user:rgarcia", source="t", scope="project:P123", record_id=rid,
                body="/remind +1h not a dispatch",
            ),
        ).key  # fmt: skip
    assert plain
    claim = Claim(plain, "thread.reminder", "project:P123", 1, 3, "w", "2099-01-01T00:00:00Z")
    with open_uow(db, readonly=True) as uow, pytest.raises(JobFailure) as raised:
        ThreadReminderKind().prepare(uow, claim)
    assert raised.value.code == "message_missing" and not raised.value.retryable
