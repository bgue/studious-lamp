"""``/dispatch <action>`` runs the integration layer's ``InvokeAction`` as the caller (ADR-0018,
FANOUT D10; P1-I7 WS-B). The real command runner decides what the caller holds."""

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
from tl_core.integration.actions.service import DefineAction, define_action
from tl_core.integration.errors import ActionAccessError
from tl_core.threads.dispatch import DispatchFromThread, handle_dispatch_from_thread
from tl_core.threads.planner import ThreadPlanner
from tl_core.webhooks.egress import EgressPolicy

RUNNER = TableRunner()
POLICY = EgressPolicy((), lambda host, port: ["93.184.216.34"])


@pytest.fixture(autouse=True)
def world(db: DbTarget) -> Iterator[None]:
    make_person(db, "rgarcia")
    with planning_world():
        yield


def define(db: DbTarget, name: str = "send_to_nde", access: str = "user") -> None:
    with open_uow(db) as uow:
        define_action(
            uow,
            DefineAction(
                actor="user:boss",
                source="t",
                scope=P1,
                name=name,
                label="Send to NDE",
                executor="webhook",
                executor_config={"url": "https://nde.example.net/hooks/request"},
                side_effect_class="external",
                access=access,  # type: ignore[arg-type]
                parameters=[
                    {"name": "urgent", "label": "Urgent"},
                    {"name": "text", "label": "Text"},
                ],
            ),
            policy=POLICY,
        )


def preview(db: DbTarget, rid: str, line: str, holds: Any = everyone) -> Any:
    planner = ThreadPlanner(factory=lambda readonly=False: open_uow(db, readonly=readonly))
    with open_uow(db, readonly=True) as uow:
        return planner.preview(
            uow, record_id=rid, text=line, actor="user:rgarcia", holds=holds, runner=RUNNER
        )


def rows(db: DbTarget, sql: str) -> list[Any]:
    with open_uow(db, readonly=True) as uow:
        return list(uow.conn().execute(text(sql)).all())


def test_dispatch_previews_and_runs_the_action_as_the_caller(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    define(db)
    line = "/dispatch send_to_nde urgent=yes please check"
    found = preview(db, rid, line)
    (item,) = found.planned
    assert item.command_type == "InvokeAction" and item.problem is None and item.permitted
    assert item.command["targets"] == [rid]
    assert item.command["parameters"] == {"urgent": "yes", "text": "please check"}
    assert found.can_dispatch and rows(db, "SELECT 1 FROM cur_action_invocation") == []
    cmd = DispatchFromThread(
        actor="user:rgarcia",
        source="tui",
        scope=P1,
        record_id=rid,
        text=line,
        token=found.token,
        expires_at=found.expires_at,
    )
    with open_uow(db) as uow:
        done = handle_dispatch_from_thread(uow, cmd, holds=everyone, runner=RUNNER)
    (invocation,) = rows(db, "SELECT action, invoked_by FROM cur_action_invocation")
    assert tuple(invocation) == ("send_to_nde", "user:rgarcia")
    kinds = [r[0] for r in rows(db, "SELECT event_type FROM events ORDER BY seq")]
    assert kinds[-3:] == ["Thread.MessagePosted", "Action.Requested", "Thread.Dispatched"]
    assert done.key


def test_an_unknown_action_is_the_plans_problem_and_writes_nothing(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    found = preview(db, rid, "/dispatch nothing_like_it")
    assert not found.can_dispatch and found.planned[0].problem is not None
    assert rows(db, "SELECT 1 FROM cur_action_invocation") == []


def test_an_action_the_caller_may_not_invoke_cannot_be_dispatched(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    define(db, access="admin")
    line = "/dispatch send_to_nde"
    found = preview(db, rid, line, holds=only_users)
    assert not found.can_dispatch
    (item,) = found.planned
    assert item.problem is not None or not item.permitted
    cmd = DispatchFromThread(
        actor="user:rgarcia",
        source="tui",
        scope=P1,
        record_id=rid,
        text=line,
        token=found.token,
        expires_at=found.expires_at,
    )
    # The confirmation does not dry-run: the handler's own refusal surfaces and nothing is written.
    with pytest.raises(ActionAccessError), open_uow(db) as uow:
        handle_dispatch_from_thread(uow, cmd, holds=only_users, runner=RUNNER)
    assert rows(db, "SELECT 1 FROM cur_action_invocation") == []
