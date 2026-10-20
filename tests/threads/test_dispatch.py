"""Confirming a dispatch: exactly what was previewed, with the caller's access (S2)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from thread_world import (
    P1,
    TableRunner,
    everyone,
    make_person,
    make_record,
    only_users,
    planning_world,
)
from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.contract import Access
from tl_core.services.commands import CommandResult
from tl_core.services.errors import GuardFailedError, SelfLinkError
from tl_core.threads.dispatch import DispatchFromThread, handle_dispatch_from_thread
from tl_core.threads.errors import (
    DispatchForbiddenError,
    DispatchRefusedError,
    DispatchStaleError,
    DispatchSyntaxError,
)
from tl_core.threads.planner import ThreadPlanner
from tl_core.threads.queries import read_thread

RUNNER = TableRunner()


@pytest.fixture(autouse=True)
def accounts(db: DbTarget) -> None:
    """The runner finds what an actor holds in its account, so the people who dispatch have one."""
    make_person(db, "rgarcia")
    make_person(db, "planner", "agent")


@pytest.fixture(autouse=True)
def world() -> Iterator[None]:
    with planning_world():
        yield


def make_planner(db: DbTarget) -> ThreadPlanner:
    return ThreadPlanner(factory=lambda readonly=False: open_uow(db, readonly=readonly))


def token_for(db: DbTarget, rid: str, line: str, actor: str = "user:rgarcia") -> Any:
    with open_uow(db, readonly=True) as uow:
        found = make_planner(db).preview(
            uow, record_id=rid, text=line, actor=actor, holds=everyone, runner=RUNNER
        )
    return found


def confirm(
    db: DbTarget,
    rid: str,
    line: str,
    token: str,
    *,
    actor: str = "user:rgarcia",
    holds: Any = everyone,
    expires_at: str | None = None,
) -> CommandResult:
    cmd = DispatchFromThread(
        actor=actor,
        source="tui",
        scope=P1,
        record_id=rid,
        text=line,
        token=token,
        expires_at=expires_at,
    )
    with open_uow(db) as uow:
        return handle_dispatch_from_thread(uow, cmd, holds=holds, runner=RUNNER)


def events(db: DbTarget) -> list[Any]:
    with open_uow(db, readonly=True) as uow:
        return list(
            uow.conn()
            .execute(
                text(
                    "SELECT event_type, source, correlation_id, causation_id, event_id, actor, "
                    "stream_id FROM events ORDER BY seq"
                )
            )
            .all()
        )


def test_raise_creates_a_linked_record_in_one_unit_with_server_set_identifiers(
    db: DbTarget,
) -> None:
    rid = make_record(db, "REC-1")
    other = make_record(db, "REC-2")
    line = "/raise record #REC-2 Clash at grid C4"
    token = token_for(db, rid, line).token
    before = len(events(db))
    result = confirm(db, rid, line, token)
    message_id = result.key
    assert message_id
    new = events(db)[before:]
    kinds = [e.event_type for e in new]
    assert kinds == [
        "Thread.MessagePosted",
        "Numbering.Allocated",
        "Record.Created",
        "Link.Added",
        "Link.Added",
        "Thread.Dispatched",
    ]
    assert {e.source for e in new} == {f"thread:{rid}"}
    assert {e.correlation_id for e in new} == {f"dispatch:{message_id}"}
    assert {e.actor for e in new} == {"user:rgarcia"}
    posted = new[0]
    assert all(e.causation_id == posted.event_id for e in new[1:])
    with open_uow(db, readonly=True) as uow:
        links = (
            uow.conn()
            .execute(
                text("SELECT from_id, to_id, relation, source FROM cur_links ORDER BY relation")
            )
            .all()
        )
        created = (
            uow.conn()
            .execute(
                text("SELECT id, key, title FROM cur_core_record WHERE title = 'Clash at grid C4'")
            )
            .one()
        )
        page = read_thread(uow, rid, actor="user:rgarcia")
    assert {(link.from_id, link.to_id, link.relation, link.source) for link in links} == {
        (created.id, rid, "dispatched_from", "thread_dispatch"),
        (created.id, other, "raised_against", "manual"),
    }
    message = page.messages[0]
    assert message.body == line and page.kinds == ["dispatch"]
    assert message.dispatch is not None and message.dispatch.verb == "raise"
    assert [r.command_type for r in message.dispatch.results] == ["CreateRecord", "AddLink"]
    assert message.dispatch.results[0].key == created.key
    assert len(message.dispatch.link_ids) == 1
    people = {p.actor: p.reasons for p in page.participants}
    assert people["user:rgarcia"] == ["author", "dispatcher"]


def test_a_changed_plan_is_stale_and_nothing_is_written(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    line = "/link REC-A"
    a = make_record(db, "REC-A")
    token = token_for(db, rid, line).token
    # the record moves on between the preview and the confirmation
    from tl_core.services.commands import UpdateRecord
    from tl_core.services.records import handle_update_record

    with open_uow(db) as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor="u",
                source="t",
                scope=P1,
                stream_id=rid,
                expected_version=1,
                changes={"title": "new"},
            ),
        )
    before = len(events(db))
    with pytest.raises(DispatchStaleError):
        confirm(db, rid, line, token)
    with pytest.raises(DispatchStaleError):
        confirm(db, rid, "/link REC-A as requires", token_for(db, rid, line).token)
    assert len(events(db)) == before and a


def test_the_token_of_another_line_is_stale(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    token = token_for(db, rid, "/link REC-A").token
    with pytest.raises(DispatchStaleError):
        confirm(db, rid, "/link REC-A as requires", token)


def test_an_expired_preview_is_stale(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    token = token_for(db, rid, "/link REC-A").token
    with pytest.raises(DispatchStaleError):
        confirm(db, rid, "/link REC-A", token, expires_at="2020-01-01T00:00:00+00:00")


def test_an_agent_never_dispatches_directly(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    token = token_for(db, rid, "/link REC-A").token
    with pytest.raises(DispatchForbiddenError):
        confirm(db, rid, "/link REC-A", token, actor="agent:planner")


def test_a_command_the_caller_may_not_run_refuses_the_whole_dispatch(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    token = token_for(db, rid, "/raise record Something").token

    def nothing(level: Access) -> bool:
        return False

    before = len(events(db))
    with pytest.raises(DispatchRefusedError) as raised:
        confirm(db, rid, "/raise record Something", token, holds=nothing)
    assert raised.value.problems and len(events(db)) == before


def test_a_failing_second_command_rolls_back_the_first(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    other = make_record(db, "REC-2")
    line = "/link REC-2 REC-3"
    make_record(db, "REC-3")
    token = token_for(db, rid, line).token
    # make the second link a duplicate after the preview: the dry run cannot know
    from tl_core.services.links import AddLink, handle_add_link

    with open_uow(db) as uow:
        handle_add_link(
            uow, AddLink(actor="u", source="t", scope=P1, from_id=rid, to_id=_id(db, "REC-3"))
        )
    before = len(events(db))
    with pytest.raises(Exception):  # noqa: B017 - the duplicate link, or the stale record version
        confirm(db, rid, line, token)
    assert len(events(db)) == before and other


def _id(db: DbTarget, key: str) -> str:
    with open_uow(db, readonly=True) as uow:
        return str(
            uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE key = :k"), {"k": key})
            .scalar_one()
        )


def test_a_refusal_of_a_handler_surfaces_unchanged_and_writes_nothing(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    line = "/link REC-1"
    token = token_for(db, rid, line).token
    before = len(events(db))
    with pytest.raises(SelfLinkError):
        confirm(db, rid, line, token, holds=only_users)
    assert len(events(db)) == before


def test_status_runs_the_transition_as_the_caller_without_roles(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    line = "/status Issued all clear"
    result = confirm(db, rid, line, token_for(db, rid, line).token)
    assert any(e.event_type == "Workflow.Transitioned" for e in result.events)
    with open_uow(db, readonly=True) as uow:
        status = (
            uow.conn()
            .execute(text("SELECT status FROM cur_core_record WHERE id = :i"), {"i": rid})
            .scalar_one()
        )
    assert status == "Issued"
    close = "/status Closed"
    preview = token_for(db, rid, close)
    assert not preview.can_dispatch  # the role guard: no role is ever taken from the caller
    with pytest.raises(GuardFailedError):
        confirm(db, rid, close, preview.token)


def test_notify_summarise_and_remind(db: DbTarget) -> None:
    make_person(db, "lchen")
    rid = make_record(db, "REC-1")
    notify = "/notify @lchen see this"
    confirm(db, rid, notify, token_for(db, rid, notify).token)
    summarise = "/summarise"
    confirm(db, rid, summarise, token_for(db, rid, summarise).token)
    remind = "/remind +1h @lchen call"
    confirm(db, rid, remind, token_for(db, rid, remind).token)
    with open_uow(db, readonly=True) as uow:
        page = read_thread(uow, rid, actor="user:x")
        job = uow.conn().execute(text("SELECT kind, state, scope FROM job_queue")).all()
    assert page.kinds == ["dispatch", "dispatch", "summary", "dispatch"]
    assert page.messages[0].dispatch is not None
    assert page.messages[0].dispatch.summary == "Notified @lchen"
    assert "Thread summary" in page.messages[2].body and page.messages[2].author == "user:rgarcia"
    assert [(j.kind, j.state, j.scope) for j in job] == [("thread.reminder", "queued", P1)]
    people = {p.actor: p.reasons for p in page.participants}
    assert people["user:lchen"] == ["mentioned"]


def test_a_plain_message_is_not_a_dispatch(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    with pytest.raises(DispatchSyntaxError):
        confirm(db, rid, "hello", "0" * 64)
    with pytest.raises(DispatchSyntaxError):
        confirm(db, rid, "/link", "0" * 64)


def test_a_token_runs_once_and_a_replay_is_stale(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    for line in ("/raise record Clash at grid C4", "/summarise", "/remind +1h call back"):
        found = token_for(db, rid, line)
        confirm(db, rid, line, found.token, expires_at=found.expires_at)
        records, written = count_rows(db, "SELECT COUNT(*) FROM cur_core_record"), len(events(db))
        with pytest.raises(DispatchStaleError):
            confirm(db, rid, line, found.token, expires_at=found.expires_at)
        assert count_rows(db, "SELECT COUNT(*) FROM cur_core_record") == records
        assert len(events(db)) == written
    kinds = [e.event_type for e in events(db)]
    assert kinds.count("Thread.Dispatched") == 3


def count_rows(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_an_expiry_that_is_not_a_time_or_not_one_a_preview_gave_is_stale(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    found = token_for(db, rid, "/link REC-A")
    for bad in ("tomorrow", "2099-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"):
        with pytest.raises(DispatchStaleError):
            confirm(db, rid, "/link REC-A", found.token, expires_at=bad)
    naive = found.expires_at.split("+")[0]  # no zone: it is UTC
    assert confirm(db, rid, "/link REC-A", found.token, expires_at=naive).key
