"""The dispatch planner: previews of every verb with the caller's access (P1-I7 WS-B, S2)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import text
from test_dispatch_contract import check_preview_shape
from thread_world import (
    P1,
    TableRunner,
    everyone,
    make_person,
    make_record,
    only_users,
    planning_world,
    put_setting,
)
from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.contract import Access
from tl_core.services.errors import RecordNotFoundError
from tl_core.threads.contract import DispatchPlanner, DispatchPreview, ParseProblem
from tl_core.threads.errors import (
    DispatchDisabledError,
    DispatchForbiddenError,
    ThreadsDisabledError,
)
from tl_core.threads.messages import PostThreadMessage, handle_post_thread_message
from tl_core.threads.planner import DispatchPlan, ThreadPlanner
from tl_core.threads.targets import TargetRegistry, core_targets

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


def planner(db: DbTarget) -> ThreadPlanner:
    from tl_adapters.db import open_uow as _open

    return ThreadPlanner(factory=lambda readonly=False: _open(db, readonly=readonly))


def plan_as_agent(db: DbTarget, record_id: str, text_: str) -> Any:
    """What a proposal is made from: an agent has no preview, only a plan with nothing run."""
    with open_uow(db, readonly=True) as uow:
        return planner(db).plan(
            uow,
            record_id=record_id,
            text=text_,
            actor="agent:planner",
            holds=everyone,
            runner=RUNNER,
        )


def preview(
    db: DbTarget,
    record_id: str,
    text_: str,
    *,
    actor: str = "user:rgarcia",
    holds: Callable[[Access], bool] = everyone,
    thread_planner: ThreadPlanner | None = None,
) -> DispatchPreview | ParseProblem:
    with open_uow(db, readonly=True) as uow:
        return (thread_planner or planner(db)).preview(
            uow, record_id=record_id, text=text_, actor=actor, holds=holds, runner=RUNNER
        )


def ok(found: DispatchPreview | ParseProblem) -> DispatchPreview:
    assert isinstance(found, DispatchPreview), found
    check_preview_shape(found)
    return found


def count(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_the_planner_is_a_dispatch_planner() -> None:
    assert isinstance(ThreadPlanner(), DispatchPlanner)


def test_a_plain_message_and_a_syntax_error_are_not_previews(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    plain = preview(db, rid, "hello")
    assert isinstance(plain, ParseProblem) and plain.code == "not_a_dispatch"
    bad = preview(db, rid, "/link")
    assert isinstance(bad, ParseProblem) and bad.code == "missing_argument"


def test_link_previews_one_addlink_per_key_and_writes_nothing(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    a, b = make_record(db, "REC-A"), make_record(db, "REC-B")
    before = count(db, "SELECT COUNT(*) FROM events")
    found = ok(preview(db, rid, "/link #REC-A REC-B as requires"))
    assert found.side_effecting and found.can_dispatch
    assert [p.command_type for p in found.planned] == ["AddLink", "AddLink"]
    assert [p.command["to_id"] for p in found.planned] == [a, b]
    assert all(p.command["relation"] == "requires" and p.access == "user" for p in found.planned)
    assert all("actor" not in p.command and "source" not in p.command for p in found.planned)
    assert count(db, "SELECT COUNT(*) FROM events") == before
    assert found.token and found.expires_at


def test_a_key_that_is_not_there_is_a_problem_of_the_preview(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    found = ok(preview(db, rid, "/link NOPE"))
    assert not found.can_dispatch and found.problems[0].code == "unknown_key"


def test_a_refusal_of_the_handler_shows_in_the_dry_run(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    found = ok(preview(db, rid, "/link REC-1"))
    assert not found.can_dispatch
    assert found.planned[0].problem is not None
    assert found.planned[0].problem.code == "command_refused"
    assert "SelfLinkError" in found.planned[0].problem.message


def test_status_finds_the_transition_by_state_label_or_name(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    for target in ("Issued", "issued for use", "issue"):
        found = ok(preview(db, rid, f'/status "{target}" ready'))
        assert found.can_dispatch, target
        planned = found.planned[0]
        assert planned.command_type == "TransitionWorkflow"
        assert planned.command["transition"] == "issue" and planned.command["reason"] == "ready"
        assert "actor_roles" not in planned.command
    unknown = ok(preview(db, rid, "/status Closed"))
    assert unknown.problems[0].code == "unknown_state" and "Issued for use" not in "x"


def test_a_failed_guard_is_the_items_problem_and_roles_are_never_supplied(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow

    with open_uow(db) as uow:
        handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor="user:a",
                source="t",
                scope=P1,
                stream_id=rid,
                expected_version=1,
                transition="issue",
            ),
        )
    found = ok(preview(db, rid, "/status Closed"))
    assert not found.can_dispatch
    problem = found.planned[0].problem
    assert problem is not None and "roles" in problem.message


def test_raise_record_creates_a_linked_record_in_the_dry_run_only(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    other = make_record(db, "REC-2")
    records = count(db, "SELECT COUNT(*) FROM cur_core_record")
    found = ok(preview(db, rid, "/raise record #REC-2 Clash at grid C4"))
    assert found.can_dispatch
    assert [p.command_type for p in found.planned] == ["CreateRecord", "AddLink"]
    assert found.planned[0].command["title"] == "Clash at grid C4"
    assert found.planned[1].command == {
        "from_id": "$result:0",
        "to_id": other,
        "relation": "raised_against",
    }
    assert len(found.links) == 1 and found.links[0].to_record_id == rid
    assert found.links[0].from_record_id is None
    assert count(db, "SELECT COUNT(*) FROM cur_core_record") == records


def test_raise_needs_a_title_and_an_rfi_is_unavailable_until_p1_i6(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    assert ok(preview(db, rid, "/raise record")).problems[0].code == "missing_argument"
    rfi = ok(preview(db, rid, "/raise rfi #REC-1 Clash"))
    assert not rfi.can_dispatch and rfi.problems[0].code == "dispatch_unavailable"
    assert rfi.planned == []


def test_assign_due_hold_and_release_are_unavailable(db: DbTarget) -> None:
    make_person(db, "lchen")
    rid = make_record(db, "REC-1")
    for line in ("/assign @lchen W1", "/due +3d", "/hold waiting", "/release"):
        found = ok(preview(db, rid, line))
        assert not found.can_dispatch and found.problems[0].code == "dispatch_unavailable", line
        assert found.side_effecting


def test_a_registered_target_makes_a_verb_available(db: DbTarget) -> None:
    from tl_core.integration.contract import PlannedCommand

    class HoldTarget:
        verb = "hold"
        name = "*"

        def plan(self, uow: Any, context: Any, parsed: Any) -> list[PlannedCommand]:
            return [
                PlannedCommand(
                    command_type="CreateRecord",
                    command={"record_type": "core.Record", "title": "Hold"},
                )
            ]

    registry = TargetRegistry()
    for target in core_targets():
        registry.register(target)
    registry.register(HoldTarget())  # type: ignore[arg-type]
    rid = make_record(db, "REC-1")
    thread_planner = ThreadPlanner(targets=registry)
    found = ok(preview(db, rid, "/hold stop", thread_planner=thread_planner))
    assert found.planned[0].command_type == "CreateRecord"


def test_dispatch_plans_an_invoke_action_on_the_thread_record(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    found = ok(preview(db, rid, "/dispatch send_to_nde qty=2 urgent"))
    assert found.planned[0].command_type == "InvokeAction"
    assert found.planned[0].command == {
        "action": "send_to_nde",
        "targets": [rid],
        "parameters": {"qty": "2", "text": "urgent"},
    }
    # The action is not defined here, so the dry run refuses it: the plan's problem, not a crash.
    assert found.planned[0].problem is not None and not found.can_dispatch


def test_access_is_the_callers_never_more(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    found = ok(preview(db, rid, "/raise record Something", holds=lambda level: False))
    assert not found.can_dispatch
    assert all(not p.permitted and p.problem is not None for p in found.planned)
    assert found.planned[0].problem is not None and found.planned[0].problem.code == "not_permitted"


def test_a_target_cannot_grant_itself_access_or_name_server_fields(db: DbTarget) -> None:
    from tl_core.integration.contract import PlannedCommand

    class Sneaky:
        verb = "hold"
        name = "*"

        def plan(self, uow: Any, context: Any, parsed: Any) -> list[PlannedCommand]:
            return [
                PlannedCommand(
                    command_type="ChangeSetting",
                    command={
                        "key": "threads.enabled",
                        "layer": "company",
                        "value": True,
                        "scope": "company",
                    },
                    access="user",
                    permitted=True,
                )
            ]

    registry = TargetRegistry()
    for target in core_targets():
        registry.register(target)
    registry.register(Sneaky())  # type: ignore[arg-type]
    rid = make_record(db, "REC-1")
    found = ok(preview(db, rid, "/hold x", thread_planner=ThreadPlanner(targets=registry)))
    assert found.planned[0].problem is not None
    assert found.planned[0].problem.code == "reserved_field"
    assert not found.planned[0].permitted and not found.can_dispatch


def test_notify_checks_the_people_and_runs_nothing(db: DbTarget) -> None:
    make_person(db, "lchen")
    rid = make_record(db, "REC-1")
    good = ok(preview(db, rid, "/notify @lchen look"))
    assert not good.side_effecting and good.can_dispatch and good.planned == []
    for line in ("/notify @nobody", "/notify @party:acme-nde", "/notify @crew:P-07"):
        bad = ok(preview(db, rid, line))
        assert bad.problems[0].code == "unknown_mention", line


def test_remind_keeps_the_time_as_typed_and_refuses_the_past(db: DbTarget) -> None:
    make_person(db, "lchen")
    rid = make_record(db, "REC-1")
    found = ok(preview(db, rid, "/remind +2h @lchen check the bevels"))
    item = found.planned[0]
    assert item.command == {"when": "+2h", "who": ["user:lchen"], "text": "check the bevels"}
    assert item.access == "user" and found.can_dispatch
    again = ok(preview(db, rid, "/remind +2h @lchen check the bevels"))
    assert again.token == found.token
    past = ok(preview(db, rid, "/remind 2020-01-01"))
    assert past.problems[0].code == "bad_time"
    alone = ok(preview(db, rid, "/remind +1d"))
    assert alone.planned[0].command["who"] == []  # the setter is read from the message (L5)
    make_person(db, "other")
    by_other = ok(preview(db, rid, "/remind +1d", actor="user:other"))
    assert by_other.token == alone.token  # the same plan whoever previews or accepts it


def test_summarise_is_a_deterministic_text_and_needs_messages(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    assert ok(preview(db, rid, "/summarise")).problems[0].code == "empty_thread"
    with open_uow(db) as uow:
        handle_post_thread_message(
            uow,
            PostThreadMessage(
                actor="user:rgarcia", source="t", scope=P1, record_id=rid, body="First line\nsecond"
            ),
        )
    first = ok(preview(db, rid, "/summarise"))
    assert not first.side_effecting and first.can_dispatch
    body = first.planned[0].command["text"]
    assert "no model" in body and "user:rgarcia: First line" in body
    assert ok(preview(db, rid, "/summarise")).token == first.token


def test_the_token_names_the_plan_and_not_who_may_run_it(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    by_user = ok(preview(db, rid, "/link REC-A", holds=only_users))
    by_all = ok(preview(db, rid, "/link REC-A", holds=everyone))
    assert by_user.token == by_all.token
    other_line = ok(preview(db, rid, "/link REC-A as requires"))
    assert other_line.token != by_all.token
    with open_uow(db) as uow:
        handle_post_thread_message(
            uow,
            PostThreadMessage(actor="user:rgarcia", source="t", scope=P1, record_id=rid, body="hi"),
        )
    assert ok(preview(db, rid, "/link REC-A")).token == by_all.token  # a message is not the record


def test_the_gate_is_the_settings_and_the_roles(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    put_setting(db, "threads.dispatch.roles", ["document_controller"])
    with pytest.raises(DispatchForbiddenError):
        preview(db, rid, "/link REC-1", holds=only_users)
    assert isinstance(
        preview(db, rid, "/hold x", holds=lambda level: level != "admin"), DispatchPreview
    )
    put_setting(db, "threads.dispatch.roles", ["admin"])
    with pytest.raises(DispatchForbiddenError):
        preview(db, rid, "/hold x", holds=lambda level: level != "admin")
    put_setting(db, "threads.dispatch.roles", [])
    put_setting(db, "threads.dispatch.enabled", False)
    with pytest.raises(DispatchDisabledError):
        preview(db, rid, "/hold x")
    put_setting(db, "threads.dispatch.enabled", True)
    put_setting(db, "threads.enabled", False)
    with pytest.raises(ThreadsDisabledError):
        preview(db, rid, "/hold x")


def test_an_agent_is_planned_for_only_while_agents_may_propose(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    put_setting(db, "threads.dispatch.roles", ["admin"])
    assert isinstance(plan_as_agent(db, rid, "/hold x"), DispatchPlan)
    put_setting(db, "threads.agents.can_dispatch", "none")
    with pytest.raises(DispatchDisabledError):
        plan_as_agent(db, rid, "/hold x")


def test_a_record_that_is_not_there_is_the_record_routes_answer(db: DbTarget) -> None:
    with pytest.raises(RecordNotFoundError):
        preview(db, "no-such-record", "/hold x")
